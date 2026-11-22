#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC Bionic: avoid scanning provably unmodified speculative readback regions.

Evidence: RedMagic 2026-11-22 10:21 profile, precise readback mode 2, hot
mode 1 and 300-520 guest readbacks/s. Upstream hot mode can inspect up to
64 * (512KiB / 64KiB capped at 4) = 256 recent regions on every readback.
For each such region GatherDownloads previously called the memory tracking
walker even if gpu_modified_ranges could not produce one byte to copy.

The SAME interval set is intersected later in GatherDownloads.add_download.
Only skip speculative regions for which that intersection is provably empty.
The explicitly requested region remains unconditional. Preserve all modified
data, guest readback ordering, async fences, heap guard and exact readback mode.
"""
from pathlib import Path

def once(code: str, old: str, new: str, label: str) -> str:
    n = code.count(old)
    if n != 1:
        raise ValueError(f"SotC 058 hot readback prune: {label} drift ({n} matches)")
    return code.replace(old, new, 1)

def patch_hot_readback_prune(gpu: Path) -> None:
    root = gpu / "shadps4/video_core"
    cpp = root / "buffer_cache/buffer_cache.cpp"
    src = cpp.read_text()
    src = once(src,
        """    boost::container::small_vector<Region, 16> regions;
    regions.push_back({arena, device_addr, size});
    if (hot_enabled) {""",
        """    boost::container::small_vector<Region, 16> regions;
    regions.push_back({arena, device_addr, size});
    // Local counters: at most one atomic update per readback, not per hot region.
    u64 sotc_hot_candidates = 0;
    u64 sotc_hot_pruned = 0;
    if (hot_enabled) {""",
        "hot region accounting")
    src = once(src,
        """            if (!hot_arena || address_space[last_page] != hot_arena ||
                (hot_mode == 1 && hot_arena != arena)) {
                continue;
            }
            regions.push_back({hot_arena, hot.addr, hot.size});""",
        """            if (!hot_arena || address_space[last_page] != hot_arena ||
                (hot_mode == 1 && hot_arena != arena)) {
                continue;
            }
            ++sotc_hot_candidates;
            // GatherDownloads only enqueues bytes in gpu_modified_ranges
            // (see add_download below). If this range doesn't intersect,
            // calling ForEachDownloadRange cannot yield a single VkBufferCopy.
            // Keep tracking the hot request itself for later GPU writes.
            // The requested region (index 0) is NEVER filtered here.
            if (!gpu_modified_ranges.Intersects(hot.addr, hot.size)) {
                ++sotc_hot_pruned;
                continue;
            }
            regions.push_back({hot_arena, hot.addr, hot.size});""",
        "safe speculative scan short-circuit")
    src = once(src,
        """    u64 total_size_bytes = 0;
    for (size_t region_index = 0; region_index < regions.size(); ++region_index) {""",
        """    if (SotcStats::kFpsLog && hot_enabled) {
        SotcStats::rb_hot_candidate_scans.fetch_add(sotc_hot_candidates,
                                                    std::memory_order_relaxed);
        SotcStats::rb_hot_empty_scans_pruned.fetch_add(sotc_hot_pruned,
                                                      std::memory_order_relaxed);
    }
    u64 total_size_bytes = 0;
    for (size_t region_index = 0; region_index < regions.size(); ++region_index) {""",
        "batched counters")
    # Preserve the existing downstream gpu_modified_ranges intersection:
    # the new check must never REPLACE the accurate actual-download test.
    for invariant in (
        "gpu_modified_ranges.ForEachInRange(address, range_size, add_download);",
        "gpu_modified_ranges.ForEachInRange(run_start, end - run_start, add_download);",
        "memory_tracker->ForEachDownloadRange<false>(",
        "const bool hot_region = region_index > 0;",
        "const bool async = [] {",
        "scheduler.GetWorkSemaphore()->Wait(readback.tick);",
    ):
        if invariant not in src:
            raise ValueError("SotC 058: required guest readback safety path absent: " + invariant)
    cpp.write_text(src)

    stats = root / "sotc_stats.h"
    code = stats.read_text()
    code = once(code,
        "inline std::atomic<uint64_t> rb_stream_windows{0};",
        """inline std::atomic<uint64_t> rb_stream_windows{0};
/// Exact speculative hot-region scans avoided, without skipping requested readbacks.
inline std::atomic<uint64_t> rb_hot_candidate_scans{0};
inline std::atomic<uint64_t> rb_hot_empty_scans_pruned{0};""",
        "profiling counters")
    stats.write_text(code)

    driver = gpu / "shadps4/core/libraries/videoout/driver.cpp"
    code = driver.read_text()
    code = once(code,
        """            static uint64_t last_images_new = 0;""",
        """            if (const u64 candidates =
                    SotcStats::rb_hot_candidate_scans.exchange(0)) {
                const u64 skipped =
                    SotcStats::rb_hot_empty_scans_pruned.exchange(0);
                std::fprintf(stderr,
                    "SOTC RB HOT PRUNE: %llu/%llu empty speculative scans skipped (%.1f%%)\\n",
                    static_cast<unsigned long long>(skipped),
                    static_cast<unsigned long long>(candidates),
                    100.0 * double(skipped) / double(candidates));
            }
            static uint64_t last_images_new = 0;""",
        "five-second effectiveness counter")
    driver.write_text(code)
    print("SotC 058: filter only empty speculative hot readback scans; precise requested data unchanged")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", type=Path, required=True)
    patch_hot_readback_prune(parser.parse_args().gpu)
