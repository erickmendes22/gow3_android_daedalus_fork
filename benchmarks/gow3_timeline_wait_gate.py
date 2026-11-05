#!/usr/bin/env python3
"""Native Vulkan timeline A/B from the REAL GoW3 Semaphore::Wait implementation.

Compiles the baseline and candidate Wait + Refresh implementations taken from
their respective Git source. Uses a real Vulkan timeline semaphore (software
Vulkan in CI), and checks pending as well as pre-signaled waits. Not Mali FPS.
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FILE = "gpu/shadps4/video_core/renderer_vulkan/vk_semaphore.cpp"
BASE = "0f919000565d556211eeefbf196bb1972fc65084"

def method(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i+1]
    raise ValueError("unterminated method "+signature)

HEADER = r"""
#define VULKAN_HPP_NO_EXCEPTIONS
#include <vulkan/vulkan.hpp>
#include <vulkan/vulkan.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <utility>
#include <limits>
using u64 = std::uint64_t;
#define ASSERT_MSG(expr, ...) do { if (!(expr)) { \
    std::fprintf(stderr,"ASSERT FAILED line %d\n",__LINE__); std::abort(); \
} } while (0)
struct Driver {
  VkDevice d{};
  mutable std::atomic<unsigned> counter_queries{0}, wait_calls{0};
  std::pair<vk::Result,u64> getSemaphoreCounterValue(vk::Semaphore sem) const {
    counter_queries.fetch_add(1, std::memory_order_relaxed);
    std::uint64_t value{};
    VkResult rc = vkGetSemaphoreCounterValue(d,static_cast<VkSemaphore>(sem),&value);
    return {static_cast<vk::Result>(rc),value};
  }
  vk::Result waitSemaphores(const vk::SemaphoreWaitInfo* info,u64 timeout) const {
    wait_calls.fetch_add(1, std::memory_order_relaxed);
    VkResult rc = vkWaitSemaphores(d,reinterpret_cast<const VkSemaphoreWaitInfo*>(info),timeout);
    return static_cast<vk::Result>(rc);
  }
};
struct Instance { Driver driver; const Driver& GetDevice() const { return driver; } };
namespace Vulkan {
struct NativeHandle {
  vk::Semaphore handle{};
  vk::Semaphore operator*() const {return handle;}
  vk::Semaphore& get() {return handle;}
};
class Semaphore {
public:
  explicit Semaphore(const Instance& i, vk::Semaphore s,bool direct):instance(i),direct_timeline_wait(direct){
    semaphore.handle=s;
  }
  void Refresh();
  void Wait(u64);
  bool IsFree(u64 t) const {return gpu_tick.load(std::memory_order_acquire)>=t;}
  u64 KnownGpuTick() const {return gpu_tick.load(std::memory_order_acquire);}
private:
  const Instance& instance;
  NativeHandle semaphore;
  std::atomic<u64> gpu_tick{0};
  bool direct_timeline_wait;
};
"""

TAIL = r"""
} // namespace Vulkan
static constexpr unsigned N=1800;
struct Context {
 VkInstance inst{};
 VkPhysicalDevice physical{};
 VkDevice device{};
 VkSemaphore sem{};
 Instance wrapper{};
 Context() {
   VkApplicationInfo app{}; app.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO;
   app.apiVersion=VK_API_VERSION_1_2;
   VkInstanceCreateInfo ici{}; ici.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
   ici.pApplicationInfo=&app;
   if (vkCreateInstance(&ici,nullptr,&inst)!=VK_SUCCESS) std::abort();
   unsigned devices=0; vkEnumeratePhysicalDevices(inst,&devices,nullptr);
   if(!devices) std::abort();
   std::vector<VkPhysicalDevice> all(devices);
   vkEnumeratePhysicalDevices(inst,&devices,all.data()); physical=all[0];
   unsigned families=0; vkGetPhysicalDeviceQueueFamilyProperties(physical,&families,nullptr);
   VkPhysicalDeviceTimelineSemaphoreFeatures timeline{};
   timeline.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_TIMELINE_SEMAPHORE_FEATURES;
   VkPhysicalDeviceFeatures2 features{}; features.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2;
   features.pNext=&timeline;
   vkGetPhysicalDeviceFeatures2(physical,&features);
   if(!timeline.timelineSemaphore) {std::fprintf(stderr,"Timeline unsupported\n");std::abort();}
   float priority=1.0f;
   VkDeviceQueueCreateInfo qci{}; qci.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
   qci.queueFamilyIndex=0;qci.queueCount=1;qci.pQueuePriorities=&priority;
   VkDeviceCreateInfo dci{};dci.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
   dci.queueCreateInfoCount=1;dci.pQueueCreateInfos=&qci;
   dci.pNext=&timeline;
   if(vkCreateDevice(physical,&dci,nullptr,&device)!=VK_SUCCESS)std::abort();
   wrapper.driver.d=device;
   VkSemaphoreTypeCreateInfo type{};type.sType=VK_STRUCTURE_TYPE_SEMAPHORE_TYPE_CREATE_INFO;
   type.semaphoreType=VK_SEMAPHORE_TYPE_TIMELINE;
   VkSemaphoreCreateInfo sci{};sci.sType=VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;sci.pNext=&type;
   if(vkCreateSemaphore(device,&sci,nullptr,&sem)!=VK_SUCCESS)std::abort();
 }
 ~Context() {vkDestroySemaphore(device,sem,nullptr);vkDestroyDevice(device,nullptr);
             vkDestroyInstance(inst,nullptr);}
 void Signal(u64 value){
   VkSemaphoreSignalInfo info{};info.sType=VK_STRUCTURE_TYPE_SEMAPHORE_SIGNAL_INFO;
   info.semaphore=sem;info.value=value;
   if(vkSignalSemaphore(device,&info)!=VK_SUCCESS)std::abort();
 }
};

static void test(const char* mode,bool pending) {
 Context context;
 Vulkan::Semaphore sem(context.wrapper,vk::Semaphore(context.sem),DIRECT);
 auto begun=std::chrono::steady_clock::now();
 if(!pending) {
   for(unsigned i=1;i<=N;++i){
     context.Signal(i);
     sem.Wait(i);
   }
 } else {
   std::atomic<unsigned> requested{0};
   std::thread producer([&] {
     for(unsigned i=1;i<=N;++i){
       while(requested.load(std::memory_order_acquire)<i)std::this_thread::yield();
       // Guarantee a pending tick for almost all iterations.
       std::this_thread::sleep_for(std::chrono::microseconds(120));
       context.Signal(i);
     }
   });
   for(unsigned i=1;i<=N;++i){
     requested.store(i,std::memory_order_release);
     sem.Wait(i);
   }
   producer.join();
 }
 auto ended=std::chrono::steady_clock::now();
 ASSERT_MSG(sem.KnownGpuTick()==N,"gpu tick lost");
 printf("TIMELINE_VK mode=%s case=%s ns_per_tick=%.3f counter_queries=%u "
        "wait_calls=%u final_gpu_tick=%llu\n",mode,
        pending?"pending":"already-signaled",
        std::chrono::duration<double,std::nano>(ended-begun).count()/N,
        context.wrapper.driver.counter_queries.load(),
        context.wrapper.driver.wait_calls.load(),
        (unsigned long long)sem.KnownGpuTick());
}

int main() {
 test("MODE",false);
 test("MODE",true);
}
"""

def build_and_run(original: str, new: str) -> str:
    body=HEADER+method(original,"void Semaphore::Refresh()")+"\n"+method(original,"void Semaphore::Wait(u64 tick)")+"\n"+TAIL.replace("DIRECT","true" if new else "false").replace("MODE","candidate" if new else "baseline")
    # The source method belongs to Vulkan namespace, matching the header.
    with tempfile.TemporaryDirectory(prefix="gow3-timeline-") as td:
        path=Path(td)/"test.cpp";exe=Path(td)/"test"
        path.write_text(body.replace("#include <limits>","#include <limits>\n#include <vector>"))
        subprocess.run(["c++","-std=c++20","-O2","-Wall","-Wextra","-Werror","-pthread",
                        str(path),"-lvulkan","-o",str(exe)],check=True)
        return subprocess.check_output([str(exe)],text=True,timeout=30)

if __name__=="__main__":
    baseline=subprocess.check_output(["git","show",f"{BASE}:{FILE}"],text=True,cwd=ROOT)
    candidate=(ROOT/FILE).read_text()
    old_out=build_and_run(baseline,False)
    new_out=build_and_run(candidate,True)
    print(old_out,end="")
    print(new_out,end="")
    def parse(line):
        return {k:float(v) for k,v in re.findall(r"(\w+)=([\d.]+)",line)}
    o=[parse(x) for x in old_out.splitlines() if x.startswith("TIMELINE_VK")]
    n=[parse(x) for x in new_out.splitlines() if x.startswith("TIMELINE_VK")]
    assert len(o)==len(n)==2
    for old,cand in zip(o,n):
        assert old["final_gpu_tick"]==cand["final_gpu_tick"]==N
        assert cand["counter_queries"]==0
        assert cand["wait_calls"]==N
        assert old["counter_queries"]>=N
        print("API_GATE",int(old["counter_queries"]),">",int(cand["counter_queries"]),
              "Vulkan counter queries; CPU wall ratio",round(
              old["ns_per_tick"]/max(cand["ns_per_tick"],1),3))
    print("PASS: real Vulkan timeline waits and tick retirement are correct.")
    print("LIMITATION: Vulkan software driver host tests, not Mali GPU ioctl or GoW3 FPS.")
