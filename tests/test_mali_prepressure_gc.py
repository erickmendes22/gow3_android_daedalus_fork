"""PanVK Mali early texture GC must not force recurring BCn recreation."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
T=(R/"gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()
L=(R/"tools/android/bionic/run-bionic.sh").read_text()
class TestMaliEarlyGc(unittest.TestCase):
    def test_late_gc_retains_safety_bounds(self):
        self.assertIn("GOW3_MALI_GC_TRIGGER_PCT=", L)
        self.assertIn("GOW3_MALI_GC_TRIGGER_PCT", T)
        self.assertIn("return 85u;", T)
        self.assertIn("return 70u;", T)
        self.assertIn("trigger_gc_memory = budget / 100 * std::min(mali_trigger_pct, mali_pressure_pct);", T)
        self.assertIn("pressure_gc_memory = budget / 100 * mali_pressure_pct;", T)
        self.assertIn("critical_gc_memory = budget / 100 * 95;", T)
    def test_observe_routine_evictions_and_keep_dirty_data(self):
        self.assertIn("if (gc_evictions || pressured || gc_downloads != 0)", T)
        self.assertIn('pressured ? "memory pressure" : "routine eviction"', T)
        self.assertIn("DownloadImageMemory(image_id, true);", T)
if __name__ == "__main__": unittest.main()
