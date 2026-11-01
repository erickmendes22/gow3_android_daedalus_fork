"""Check PanVK bounded renderer stage captures and included ZIP export."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRESENTER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text()
FRAME = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_frame_capture.cpp").read_text()
HEADER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.h").read_text()
SHELL = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()
ARCHIVE = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/data/LogArchive.kt").read_text()


class MaliStageCapture(unittest.TestCase):
    def test_panvk_only_and_opt_out(self):
        self.assertIn("*/libvulkan_panfrost.so)", SHELL)
        self.assertIn("GOW3_MALI_AUTOCAPTURE=0", SHELL)
        self.assertIn("vendorID == 0x13B5", PRESENTER)

    def test_bounded_stages(self):
        for n in (120, 360, 480, 720):
            self.assertIn(f"mali_index == {n}", PRESENTER)
        for stage in ('"guest"', '"post"'):
            self.assertIn(stage, PRESENTER)
        self.assertIn('cpu_%03u_', PRESENTER)
        self.assertIn("max_width = 960, max_height = 540", PRESENTER)
        self.assertIn("mali_capture_frame", HEADER)
        self.assertIn("frame->mali_capture_frame = 0;", PRESENTER)

    def test_fenced_render_stage_readback(self):
        self.assertIn("scheduler.DeferPriorityOperation(", PRESENTER)
        self.assertIn("vmaInvalidateAllocation(", PRESENTER)
        self.assertIn("WriteMaliCaptureBmp(file,", PRESENTER)
        self.assertIn("waitForFences(frame->present_done, true, ~0ull)", PRESENTER)
        self.assertIn("GOW3_MALI_CAPTURE stage=cpu", PRESENTER)

    def test_stage_provenance_and_zip(self):
        self.assertIn("image.backing->image.image_ci.format", PRESENTER)
        self.assertIn("frame->image, vk::ImageLayout::eGeneral", PRESENTER)
        self.assertIn("flip_index == 119 || flip_index == 479", FRAME)
        self.assertIn('GOW3_CAPTURE_DIR="$GOW3_MALI_CAPTURE_DIR"', SHELL)
        self.assertIn('GOW3_MALI_CAPTURE_DIR="$base/logs/mali-captures"', SHELL)
        self.assertIn("logs.walkTopDown().forEach", ARCHIVE)
        self.assertIn("ZipEntry(relative)", ARCHIVE)

if __name__ == "__main__":
    unittest.main()
