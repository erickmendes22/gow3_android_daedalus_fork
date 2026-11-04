"""Static regression guards for Mali CPU-present resolution and fallback."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRES = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text()
SH = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()


class MaliPresentSourceResolution(unittest.TestCase):
    def test_opt_in_by_driver_and_rollback(self):
        self.assertIn("*/libvulkan_panfrost.so)", SH)
        self.assertIn("GOW3_MALI_PRESENT_REDUCE=${GOW3_MALI_PRESENT_REDUCE:-1}", SH)
        self.assertIn('std::getenv("GOW3_MALI_PRESENT_REDUCE")', PRES)
        self.assertIn("if (!reduce || reduce[0] != '0')", PRES)
        self.assertIn("if (swapchain.UsesCpuPresentation())", PRES)

    def test_resize_precedes_frame_acquisition_and_readback(self):
        first = PRES.index("Frame* Presenter::PrepareFrame(")
        acquire = PRES.index("Frame* frame = GetRenderFrame(true);", first)
        size = PRES.index("SetExpectedGameSize(s32(target_w), s32(target_h));", first)
        self.assertLess(size, acquire)
        self.assertIn("const vk::Extent2D output = swapchain.GetExtent()", PRES)
        self.assertIn("verified_patch.width <= output.width", PRES)
        self.assertIn("verified_patch.height <= output.height", PRES)
        self.assertIn("cmdbuf.copyImageToBuffer(frame->image,", PRES)
        self.assertIn("waitForFences(frame->present_done, true, ~0ull)", PRES)
        self.assertIn("swapchain.PresentCpuPixels(", PRES)

    def test_patch_only_when_verified_by_launch_env(self):
        self.assertIn('"GOW3_RESOLUTION_STATUS"', PRES)
        self.assertIn('"verified-direct-game-patch"', PRES)
        self.assertIn('"GOW3_PATCH_INPUT_RES"', PRES)
        self.assertIn('std::sscanf(input, "%ux%u%c"', PRES)
        self.assertIn("w >= 320 && h >= 180", PRES)

    def test_direct_patch_resolution_contract(self):
        launch = (ROOT / "scripts/launch_env.py").read_text()
        self.assertIn("updates['GOW3_PATCH_INPUT_RES']", launch)
        self.assertIn("updates['GOW3_RESOLUTION_STATUS'] = 'verified-direct-game-patch'", launch)


if __name__ == "__main__":
    unittest.main()
