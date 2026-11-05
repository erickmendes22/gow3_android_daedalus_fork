"""Mali cache GC upper headroom + hot draw environment gating."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
SH = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()
RASTER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
CACHE = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()
class MaliMenuFastpathTests(unittest.TestCase):
    def test_budget_preserves_rollback_and_critical(self):
        self.assertIn("GOW3_MALI_GC_PRESSURE_PCT=${GOW3_MALI_GC_PRESSURE_PCT:-85}", SH)
        self.assertIn("critical_gc_memory = budget / 100 * 95", CACHE)
        self.assertIn("parsed < 85 || parsed > 90", CACHE)
    def test_fixed_launcher_values_cached_in_draw(self):
        self.assertIn("static const bool gsr2_bionic = []", RASTER)
        self.assertIn("static const bool direct_videoout =", RASTER)
        self.assertIn("static const bool camera_feed_requested = []", RASTER)
        self.assertIn("static const bool gsr2_forward_enabled = []", RASTER)
if __name__ == "__main__":
    unittest.main()
