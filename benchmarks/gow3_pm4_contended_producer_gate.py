#!/usr/bin/env python3
"""One-core producer-contention gate for Mali PM4 coroutine backoff.

Extracts the actual Liverpool::Task coroutine type from production source.
Baseline and candidate share a single CPU core with a producer that performs
35ms of ACTUAL CPU work rather than simply sleeping. This captures the
thread-contention mechanism without claiming any GPU/device FPS.
"""
from pathlib import Path
import importlib.util
import re
import statistics
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
EXISTING=ROOT/"benchmarks/gow3_pm4_idle_coroutine_gate.py"
spec=importlib.util.spec_from_file_location("gow3_pm4_idle",EXISTING)
idle=importlib.util.module_from_spec(spec)
spec.loader.exec_module(idle)

CPP=r"""
#include <atomic>
#include <chrono>
#include <coroutine>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <thread>
#include <time.h>
#include <vector>
#include <pthread.h>
#include <sched.h>
#include <algorithm>
#define UNREACHABLE_MSG(...) std::abort()
class TestGpu {
public:
TASK_TYPE
 Task Await(std::atomic<bool>& flag, bool& blocked) {
   while (!flag.load(std::memory_order_acquire)) {
     blocked = true;
     co_yield {};
     blocked = false;
   }
   co_return;
 }
};
static double cpu_ms() {
 timespec tv{};
 clock_gettime(CLOCK_THREAD_CPUTIME_ID, &tv);
 return tv.tv_sec*1000.0 + tv.tv_nsec/1e6;
}
static double wall_ms() {
 return std::chrono::duration<double,std::milli>(
   std::chrono::steady_clock::now().time_since_epoch()).count();
}
static void on_same_cpu() {
 cpu_set_t allowed{};
 if(pthread_getaffinity_np(pthread_self(),sizeof(allowed),&allowed))std::abort();
 int first=-1;
 for(int i=0;i<CPU_SETSIZE;i++)if(CPU_ISSET(i,&allowed)){first=i;break;}
 if(first<0)std::abort();
 CPU_ZERO(&allowed);
 CPU_SET(first,&allowed);
 if(pthread_setaffinity_np(pthread_self(),sizeof(allowed),&allowed))std::abort();
}
struct Measurement {
 double wall{},main_cpu{},producer_wall{},producer_cpu{},release_lag{};
 unsigned resumes{};
};
static Measurement run(int backoff_us,double producer_target_cpu_ms) {
 TestGpu gpu;
 std::atomic<bool> ready{false};
 bool blocked=false;
 auto task=gpu.Await(ready,blocked);
 std::atomic<double> producer_wall{0},producer_cpu{0},signaled_at{0};
 std::thread producer([&] {
   on_same_cpu();
   const double start_cpu=cpu_ms(),start_wall=wall_ms();
   volatile double x=1;
   while(cpu_ms()-start_cpu<producer_target_cpu_ms) {
     for(int i=0;i<1000;++i) x=x*1.0000001+0.00000001;
   }
   producer_cpu.store(cpu_ms()-start_cpu,std::memory_order_relaxed);
   producer_wall.store(wall_ms()-start_wall,std::memory_order_relaxed);
   signaled_at.store(wall_ms(),std::memory_order_release);
   ready.store(true,std::memory_order_release);
 });
 const double before_cpu=cpu_ms(),before_wall=wall_ms();
 unsigned resumes=0;
 do {
   task.handle.resume();
   ++resumes;
   // Matches the branch: ONLY a blocked PM4 fiber with one queued submit.
   if(backoff_us && blocked && !task.handle.done()) {
     std::this_thread::sleep_for(std::chrono::microseconds(backoff_us));
   }
 } while(!task.handle.done());
 const double after_cpu=cpu_ms(),after_wall=wall_ms();
 task.handle.destroy();
 producer.join();
 return {after_wall-before_wall,after_cpu-before_cpu,
         producer_wall.load(),producer_cpu.load(),
         after_wall-signaled_at.load(),resumes};
}
int main(){
 on_same_cpu();
 for(int repetition=0;repetition<5;++repetition) {
   for(int us : {0,20}) {
     const auto m=run(us,35);
     printf("PM4_COMPETE repetition=%d backoff_us=%d wall_ms=%.3f "
            "gpu_cpu_ms=%.3f producer_wall_ms=%.3f "
            "producer_cpu_ms=%.3f release_lag_ms=%.3f resumes=%u\n",
            repetition,us,m.wall,m.main_cpu,m.producer_wall,
            m.producer_cpu,m.release_lag,m.resumes);
   }
 }
}
"""

def main():
    liverpool=(ROOT/"gpu/shadps4/video_core/amdgpu/liverpool.cpp").read_text()
    for needle in (
        "gfx_blocked_fiber_wait = true;",
        "gfx_blocked_fiber_wait = false;",
        "GOW3_MALI_PM4_IDLE_BACKOFF_US",
        "std::this_thread::sleep_for(std::chrono::microseconds(idle_backoff_us));",
        "num_submits.load(std::memory_order_relaxed) == 1",
        "num_commands.load(std::memory_order_relaxed) == 0",
    ):
        if needle not in liverpool:
            raise AssertionError(f"Expected production PM4 backoff guard: {needle}")
    source=CPP.replace("TASK_TYPE",idle.task_type())
    with tempfile.TemporaryDirectory(prefix="gow3-pm4-compete-") as td:
        cpp=Path(td)/"producer.cpp";exe=Path(td)/"producer"
        cpp.write_text(source)
        subprocess.run(["c++","-std=c++20","-O2","-pthread","-Wall","-Wextra",
                        "-Werror",str(cpp),"-o",str(exe)],check=True)
        text=subprocess.check_output([str(exe)],text=True,timeout=20)
    print(text,end="")
    by_mode={0:[],20:[]}
    for line in text.splitlines():
        if not line.startswith("PM4_COMPETE "):
            continue
        metrics={key:float(value) for key,value in
                 re.findall(r"([a-z_]+)=([\d.]+)",line)}
        by_mode[int(metrics["backoff_us"])].append(metrics)
    if not all(len(group)==5 for group in by_mode.values()):
        raise AssertionError("Five pairs of identical workload not collected")
    old=statistics.median(row["wall_ms"] for row in by_mode[0])
    new=statistics.median(row["wall_ms"] for row in by_mode[20])
    old_cpu=statistics.median(row["gpu_cpu_ms"] for row in by_mode[0])
    new_cpu=statistics.median(row["gpu_cpu_ms"] for row in by_mode[20])
    work=statistics.median(row["producer_cpu_ms"] for row in by_mode[20])
    saving=old-new
    print(f"PM4_CONTENDED_RESULT baseline={old:.3f}ms candidate={new:.3f}ms "
          f"wall_saved={saving:.3f}ms improvement_pct={100*saving/old:.1f}% "
          f"gpu_thread_cpu_saved={old_cpu-new_cpu:.3f}ms producer_cpu={work:.3f}ms")
    assert 34.5<=work<=36.5, "Candidate producer did not complete same 35ms work"
    assert old_cpu-new_cpu>20, "Not an effective GPU thread idle mitigation"
    assert saving>=10.0, "Reject APK: insufficient synthetic producer completion gain"
    assert new<old*.85, "Reject APK: contention effect not compelling"
    assert all(row["release_lag_ms"]<2 for row in by_mode[20])
    print("PASS: same CPU, same useful producer work, >=10ms less wall-time stall.")
    print("ACTUAL GAME FPS STILL UNKNOWN: this is sufficient to authorize "
          "an ISOLATED tester APK, not to claim any achieved device FPS gain.")

if __name__=="__main__":
    main()
