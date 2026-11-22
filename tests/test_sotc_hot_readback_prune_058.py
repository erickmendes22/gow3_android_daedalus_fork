#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Source-contract tests for precise speculative readback no-work pruning."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_sotc_hot_readback_prune_058 import patch_hot_readback_prune


def fixture():
    cpp = """    boost::container::small_vector<Region, 16> regions;
    regions.push_back({arena, device_addr, size});
    if (hot_enabled) {
            if (!hot_arena || address_space[last_page] != hot_arena ||
                (hot_mode == 1 && hot_arena != arena)) {
                continue;
            }
            regions.push_back({hot_arena, hot.addr, hot.size});
    u64 total_size_bytes = 0;
    for (size_t region_index = 0; region_index < regions.size(); ++region_index) {
    gpu_modified_ranges.ForEachInRange(address, range_size, add_download);
    gpu_modified_ranges.ForEachInRange(run_start, end - run_start, add_download);
    memory_tracker->ForEachDownloadRange<false>(
    const bool hot_region = region_index > 0;
    const bool async = [] {
    scheduler.GetWorkSemaphore()->Wait(readback.tick);"""
    stats = "inline std::atomic<uint64_t> rb_stream_windows{0};"
    driver = "            static uint64_t last_images_new = 0;"
    return cpp, stats, driver


class HotPruneTest(unittest.TestCase):
    def create_files(self, root: Path):
        cpp, stats, driver = fixture()
        for rel, value in (
            ("shadps4/video_core/buffer_cache/buffer_cache.cpp", cpp),
            ("shadps4/video_core/sotc_stats.h", stats),
            ("shadps4/core/libraries/videoout/driver.cpp", driver),
        ):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(value)

    def test_stage_only_speculative_and_preserve_real_download(self):
        with tempfile.TemporaryDirectory() as td:
            gpu = Path(td)
            self.create_files(gpu)
            patch_hot_readback_prune(gpu)
            source = (gpu / "shadps4/video_core/buffer_cache/buffer_cache.cpp").read_text()
            requested = source.index("regions.push_back({arena, device_addr, size});")
            quick = source.index("gpu_modified_ranges.Intersects(hot.addr, hot.size)")
            speculative = source.index("regions.push_back({hot_arena, hot.addr, hot.size});")
            self.assertLess(requested, quick)
            self.assertLess(quick, speculative)
            self.assertEqual(source.count("gpu_modified_ranges.ForEachInRange"), 2)
            self.assertIn("const bool hot_region = region_index > 0;", source)
            self.assertIn("scheduler.GetWorkSemaphore()->Wait(readback.tick);", source)
            self.assertIn("SotcStats::rb_hot_empty_scans_pruned.fetch_add", source)
            self.assertIn("SOTC RB HOT PRUNE:", (gpu / "shadps4/core/libraries/videoout/driver.cpp").read_text())
            with self.assertRaises(ValueError):
                patch_hot_readback_prune(gpu)

    def test_fails_closed_on_missing_readback_invariant(self):
        with tempfile.TemporaryDirectory() as td:
            gpu = Path(td)
            self.create_files(gpu)
            cpp = gpu / "shadps4/video_core/buffer_cache/buffer_cache.cpp"
            cpp.write_text(cpp.read_text().replace("scheduler.GetWorkSemaphore()->Wait(readback.tick);", ""))
            with self.assertRaises(ValueError):
                patch_hot_readback_prune(gpu)


if __name__ == "__main__":
    unittest.main()
