#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Android-only true CPU-time and page-fault counters for SotC draw profiling.

The pinned PC renderer's Linux implementation *always returns zero* from
SplitThreadCycles / SplitProcessFaults. Reuse its existing per-frame
SOTC_FPS/SOTC_DRAW_SPLIT instrumentation, but make those counter sources
accurate on Bionic. All clock calls are guarded by kDrawSplit (OFF by default).

This is diagnostic-only. It does not alter Vulkan commands or guest memory.
"""
from pathlib import Path


def patch_profile(gpu: Path) -> None:
    path = gpu / "shadps4/video_core/sotc_stats.cpp"
    src = path.read_text()

    header = '#include "video_core/sotc_stats.h"\n'
    imports = '''#include "video_core/sotc_stats.h"
#if defined(__ANDROID__)
#include <pthread.h>
#include <time.h>
#include <sys/resource.h>
#endif
'''
    if src.count(header) != 1:
        raise ValueError("SotC perf profile: stats header source drift")
    src = src.replace(header, imports)

    old = '''#else
void RegisterSplitThread(SplitThread) {}

uint64_t SplitThreadCycles(SplitThread) {
    return 0;
}

uint64_t SplitProcessFaults() {
    return 0;
}
#endif'''
    replacement = '''#elif defined(__ANDROID__)
// The upstream POSIX fallback returned 0 CPU cycles and 0 page faults.
// Keep stable independent clocks for the three long-lived native GPU threads:
// draw, command processor and Vulkan recorder. These are CPU time clocks
// (excluding sleeps and GPU fence waits), not elapsed time.
static std::atomic<clockid_t> cpu_clock_id[SplitThreads]{};
static std::atomic<bool> cpu_clock_ready[SplitThreads]{};

void RegisterSplitThread(SplitThread which) {
    if (!kDrawSplit) return;
    clockid_t id{};
    if (pthread_getcpuclockid(pthread_self(), &id) != 0) return;
    cpu_clock_id[which].store(id, std::memory_order_relaxed);
    cpu_clock_ready[which].store(true, std::memory_order_release);
}

uint64_t SplitThreadCycles(SplitThread which) {
    if (!kDrawSplit || !cpu_clock_ready[which].load(std::memory_order_acquire))
        return 0;
    struct timespec tv{};
    if (clock_gettime(cpu_clock_id[which].load(std::memory_order_relaxed), &tv) != 0)
        return 0;
    // SplitTimer::Ticks uses cntvct_el0 (fixed counter), not CPU frequency.
    // Convert thread CPU nanoseconds to that same tick domain.
    static const uint64_t tick_hz = [] {
        uint64_t frequency = 0;
        asm volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
        return frequency;
    }();
    const uint64_t ns = uint64_t(tv.tv_sec) * 1000000000ULL + uint64_t(tv.tv_nsec);
    return tick_hz ? uint64_t((__uint128_t(ns) * tick_hz) / 1000000000ULL) : 0;
}

uint64_t SplitProcessFaults() {
    if (!kDrawSplit) return 0;
    struct rusage usage{};
    if (getrusage(RUSAGE_SELF, &usage) != 0) return 0;
    return uint64_t(usage.ru_minflt) + uint64_t(usage.ru_majflt);
}
#else
void RegisterSplitThread(SplitThread) {}

uint64_t SplitThreadCycles(SplitThread) { return 0; }
uint64_t SplitProcessFaults() { return 0; }
#endif'''
    if src.count(old) != 1:
        raise ValueError("SotC perf profile: pinned POSIX fallback changed")
    src = src.replace(old, replacement)
    path.write_text(src)
    print("SotC Android perf profile: actual draw/CP/recorder thread CPU time "
          "and page faults; instrumentation disabled by default")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gpu", type=Path, required=True)
    patch_profile(ap.parse_args().gpu)
