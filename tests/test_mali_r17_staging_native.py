"""R17 source guards for asynchronous staging ownership and exact presentation."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu/shadps4/video_core/renderer_vulkan"
POOL = (VK / "vk_staging_buffer_pool.cpp").read_text()
HDR = (VK / "vk_staging_buffer_pool.h").read_text()
TEX = (VK.parent / "texture_cache/texture_cache.cpp").read_text()
PRES = (VK / "vk_presenter.cpp").read_text()
SH = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()

class R17(unittest.TestCase):
    def test_staging_public_mutators_share_lock(self):
        self.assertIn("std::mutex pool_mutex;", HDR)
        for name in ("Request", "FreeDeferred", "TickFrame"):
            start = POOL.index("StagingBufferPool::" + name + "(")
            body = POOL.index("{", start)
            self.assertTrue(POOL[body+1:].lstrip().startswith("std::scoped_lock lock{pool_mutex};"), name)
        self.assertIn("Reserve(size, alignment, false)", POOL)
    def test_priority_release_uses_completed_tick(self):
        self.assertIn("completed_tick = scheduler.CurrentTick()", TEX)
        self.assertIn("FreeDeferred(download, completed_tick)", TEX)
    def test_native_extent_preserves_verified_pixels(self):
        self.assertIn("unset GOW3_MALI_PRESENT_NATIVE_EXTENT", SH)
        self.assertEqual(SH.count("export GOW3_MALI_PRESENT_NATIVE_EXTENT=1"), 2)
        self.assertIn('std::getenv("GOW3_MALI_PRESENT_NATIVE_EXTENT")', PRES)
        self.assertIn("expected_frame_width = target_w;", PRES)
        self.assertIn("expected_frame_height = target_h;", PRES)

if __name__ == "__main__":
    unittest.main()
