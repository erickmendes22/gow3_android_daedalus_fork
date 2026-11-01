"""PanVK native pass image capture must record real GPU color/depth, with
tracked layout transitions, bounded snapshots, readable BMP and ZIP export.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PASS = (ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_mali_pass_capture.h").read_text()
RASTER = (ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
SHELL = (ROOT/"tools/android/bionic/run-bionic.sh").read_text()
ARCHIVE = (ROOT/"android-launcher/app/src/main/java/com/gow3/android/data/LogArchive.kt").read_text()


class MaliAttachmentCapture(unittest.TestCase):
    def test_vulkan_hpp_project_configuration_precedes_types(self):
        # No direct vulkan.hpp inclusion before the project's vk_common macros:
        # it breaks the whole rasterizer translation unit, not just the capture.
        self.assertIn('#include "video_core/renderer_vulkan/vk_common.h"', PASS)
        self.assertNotIn("#include <vulkan/vulkan.hpp>", PASS)
        self.assertIn("vk::BufferImageCopy copy{};", PASS)

    def test_reads_real_attachment_after_draw_both_paths(self):
        self.assertIn('#include "video_core/renderer_vulkan/vk_mali_pass_capture.h"', RASTER)
        self.assertEqual(RASTER.count("MaliPassCapture::CaptureDraw("), 2)
        self.assertIn("scheduler.EndRendering();", PASS)
        self.assertIn("runtime.Transit(&image, vk::ImageLayout::eTransferSrcOptimal", PASS)
        self.assertIn("runtime.FlushBarriers();", PASS)
        self.assertIn("copyImageToBuffer(", PASS)
        self.assertIn("scheduler.DeferPriorityOperation(", PASS)
        self.assertIn("vmaInvalidateAllocation(", PASS)

    def test_captures_color_and_depth_from_gpu_not_videoout(self):
        self.assertIn("texture_cache.GetImage(cb_descs[cb].first)", RASTER)
        self.assertIn("texture_cache.GetImage(db_desc.first)", RASTER)
        self.assertIn("vk::ImageAspectFlagBits::eDepth", PASS)
        self.assertIn("vk::ImageAspectFlagBits::eColor", PASS)
        self.assertIn("vk::ImageAspectFlagBits::eStencil", PASS)
        self.assertIn('"_stencil.bmp"', PASS)
        self.assertIn("scene_%04u_%s", PASS)
        self.assertIn('"_depth.bmp"', PASS)
        self.assertIn('"_pass.txt"', PASS)
        self.assertIn("ps_hash", PASS)
        self.assertIn("mrt_mask", PASS)

    def test_bounded_and_mali_only(self):
        self.assertIn('std::getenv("GOW3_MALI_AUTOCAPTURE")', PASS)
        self.assertIn("vendorID == 0x13B5", PASS)
        for n in (1, 8, 32, 128, 512):
            self.assertIn(f"number == {n}", PASS)
        self.assertIn("first_color_only", PASS)
        self.assertIn("std::atomic<u32> depth_draws", PASS)
        self.assertIn("first_color_only.exchange(true", PASS)
        self.assertIn("32ull << 20", PASS)
        self.assertIn("ci.samples != vk::SampleCountFlagBits::e1", PASS)
        self.assertIn("ci.usage & vk::ImageUsageFlagBits::eTransferSrc", PASS)

    def test_snapshots_are_not_gpu_writes(self):
        self.assertIn("VK_BUFFER_USAGE_TRANSFER_DST_BIT", PASS)
        self.assertIn("SaveBmp(path", PASS)
        self.assertIn("preview_w = 960, preview_h = 540", PASS)
        self.assertIn("vk::Format::eD32Sfloat", PASS)
        self.assertIn("vk::Format::eR16G16B16A16Sfloat", PASS)
        self.assertIn("GOW3_MALI_PASS_IMAGE", PASS)

    def test_export_contains_scene_captures(self):
        self.assertIn('GOW3_MALI_CAPTURE_DIR="$base/logs/mali-captures"', SHELL)
        self.assertIn('"$GOW3_MALI_CAPTURE_DIR"/scene_*.bmp', SHELL)
        self.assertIn("logs.walkTopDown().forEach", ARCHIVE)
        self.assertIn("ZipEntry(relative)", ARCHIVE)


if __name__ == "__main__":
    unittest.main()
