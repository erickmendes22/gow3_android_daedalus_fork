#!/usr/bin/env python3
"""PM4 coroutine wait backoff: CPU occupancy and completion latency on host.

Compiles Liverpool's REAL Task coroutine type extracted from liverpool.h and
models the very same while(num_submits)/task.resume() scheduler. Not GoW3
device evidence: no guest WaitRegMem opcode count in the existing log.
"""
import re
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
H=ROOT/"gpu/shadps4/video_core/amdgpu/liverpool.h"
CPP=ROOT/"gpu/shadps4/video_core/amdgpu/liverpool.cpp"

def task_type():
    t=H.read_text()
    begin=t.index("    struct Task {")
    end=t.index("\n    using CmdBuffer",begin)
    snippet=t[begin:end]
    assert snippet.strip().endswith("};")
    return snippet

HEAD=r"""
#include <atomic>
#include <chrono>
#include <coroutine>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <thread>
#include <time.h>
#include <vector>
#define UNREACHABLE_MSG(...) std::abort()
class TestGpu {
public:
TASK_TYPE
 Task Await(std::atomic<bool>& flag, bool& blocked) {
   while (!flag.load(std::memory_order_acquire)) {
     blocked=true;
     co_yield {};
     blocked=false;
   }
   co_return;
 }
};
static double cpu_ms() {
 timespec tv{};
 clock_gettime(CLOCK_THREAD_CPUTIME_ID,&tv);
 return tv.tv_sec*1000.0+tv.tv_nsec/1e6;
}
static double wall_ms() {
 return std::chrono::duration<double,std::milli>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}
struct Measurement {double cpu{},wall{},latency{}; unsigned resumes{};};
static Measurement run(int us,unsigned pending,bool already_ready){
 TestGpu gpu;
 std::atomic<bool> ready{already_ready};
 bool blocked=false;
 auto task=gpu.Await(ready,blocked);
 std::atomic<double> signaled_at{0};
 std::thread producer;
 if(!already_ready) producer=std::thread([&] {
   std::this_thread::sleep_for(std::chrono::milliseconds(35));
   signaled_at.store(wall_ms(),std::memory_order_release);
   ready.store(true,std::memory_order_release);
 });
 const double begin_cpu=cpu_ms(),begin_wall=wall_ms();
 unsigned resumes=0;
 do {
   task.handle.resume();
   ++resumes;
   // The candidate branch uses this check ONLY for the sole blocked PM4 fiber.
   if(us && blocked && pending==1 && !task.handle.done())
     std::this_thread::sleep_for(std::chrono::microseconds(us));
 } while(!task.handle.done());
 const double end_cpu=cpu_ms(),end_wall=wall_ms();
 task.handle.destroy();
 if(producer.joinable()) producer.join();
 if(!already_ready && !ready.load(std::memory_order_acquire))std::abort();
 return {end_cpu-begin_cpu,end_wall-begin_wall,
         already_ready?0.0:end_wall-signaled_at.load(std::memory_order_acquire),resumes};
}
int main(){
 for(int us:{0,20}){
    const char* mode=us?"candidate":"baseline";
    auto solo=run(us,1,false);
    auto active=run(us,2,false);
    auto ready=run(us,1,true);
    std::printf("PM4_IDLE mode=%s sole_blocked_cpu_ms=%.3f sole_wall_ms=%.3f "
       "sole_release_lag_ms=%.3f sole_resumes=%u active_cpu_ms=%.3f "
       "active_resumes=%u ready_cpu_ms=%.4f\n",
       mode,solo.cpu,solo.wall,solo.latency,solo.resumes,
       active.cpu,active.resumes,ready.cpu);
 }
}
"""

def main():
    cpp=CPP.read_text()
    for needle in ("gfx_blocked_fiber_wait = true;","gfx_blocked_fiber_wait = false;",
                   "std::this_thread::sleep_for(std::chrono::microseconds(idle_backoff_us));",
                   "num_submits.load(std::memory_order_relaxed) == 1",
                   "num_commands.load(std::memory_order_relaxed) == 0",
                   "GOW3_MALI_PM4_IDLE_BACKOFF_US"):
        if needle not in cpp:raise ValueError("Production blocked-fiber logic missing: "+needle)
    text=HEAD.replace("TASK_TYPE",task_type())
    with tempfile.TemporaryDirectory(prefix="gow3-pm4-spin-") as td:
        source=Path(td)/"test.cpp"; binary=Path(td)/"test"
        source.write_text(text)
        subprocess.run(["c++","-std=c++20","-O2","-pthread","-Wall",
                        "-Wextra","-Werror",str(source),"-o",str(binary)],check=True)
        output=subprocess.check_output([str(binary)],text=True,timeout=15)
    print(output,end="")
    data={}
    for line in output.splitlines():
        if not line.startswith("PM4_IDLE"):continue
        d={k:float(v) for k,v in re.findall(r"([a-z_]+)=([\d.]+)",line)}
        data[line.split("mode=",1)[1].split()[0]]=d
    old=data["baseline"];new=data["candidate"]
    assert old["sole_blocked_cpu_ms"]>20, "Host baseline did not busy spin"
    assert new["sole_blocked_cpu_ms"]<4, "Backoff did not reduce CPU occupancy"
    assert new["sole_release_lag_ms"]<2, "Blocked wait release latency too high"
    assert new["active_cpu_ms"]>20, "Candidate slept with other runnable PM4 submits"
    print("PASS: blocked-only backoff saves >10ms CPU in a 35ms synthetic wait.")
    print("LIMITATION: this does NOT prove G615 has these waits or improve FPS. "
          "No APK authorized without observed frequent blocked yields in real PM4.")

if __name__=="__main__":main()
