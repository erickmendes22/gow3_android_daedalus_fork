"""Protect the real native-to-native GSR2 correspondence path on Android.

These are source-contract tests. They are not an on-device Vulkan/visual pass.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VK = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_gsr2.cpp").read_text(encoding="utf-8")
UPSCALE = (ROOT / "gpu/shadps4/video_core/host_shaders/gsr2_upscale.comp").read_text(encoding="utf-8")


class NativeTemporalCorrespondence(unittest.TestCase):
    def test_native_previous_frame_is_separate_from_reconstructed_history(self):
        self.assertIn("previous_native_ycocg_image", VK)
        self.assertIn("previous_native_ycocg_view", VK)
        self.assertIn("MakeImage(previous_native_ycocg_image", VK)
        self.assertIn("image(*nearest, *previous_native_ycocg_view)", VK)
        self.assertIn("uniform usampler2D PreviousNativeYCoCg;", UPSCALE)
        self.assertNotIn("Gow3HistoryPatchError", UPSCALE)

    def test_convert_and_upscale_descriptor_counts(self):
        self.assertIn("const u32 count = native_history ? 6u : 5u;", VK)
        self.assertIn("make_layout(convert_layout, convert_pipeline_layout, false)", VK)
        self.assertIn("make_layout(upscale_layout, upscale_pipeline_layout, true)", VK)
        self.assertIn("const std::array<vk::DescriptorImageInfo, 5> infos", VK)
        self.assertIn("const std::array<vk::WriteDescriptorSet, 5> writes", VK)
        self.assertIn("const std::array<vk::DescriptorImageInfo, 6> infos", VK)
        self.assertIn("const std::array<vk::WriteDescriptorSet, 6> writes", VK)
        self.assertIn("write(5, sampled, &infos[5])", VK)

    def test_native_previous_is_copied_only_after_upscale(self):
        upscale = VK.index("cmd.dispatch((frame.output_width + 7) / 8")
        transfer = VK.index("const std::array<vk::ImageMemoryBarrier2, 2> copy_barriers")
        copy = VK.index("cmd.copyImage(vk::Image(ycocg_image)")
        advance = VK.index("current = previous;")
        self.assertLess(upscale, transfer)
        self.assertLess(transfer, copy)
        self.assertLess(copy, advance)

    def test_verified_scene_jitter_does_not_touch_hud_or_unmatched_buffers(self):
        raster = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
        self.assertIn("Gow3VerifiedNativeJitterTarget(", raster)
        self.assertIn('std::getenv("GOW3_GSR2_PREHUD")', raster)
        self.assertIn('std::getenv("GOW3_GSR2_INPUT_RES")', raster)
        self.assertIn('FrameCapture::IsDisplayBuffer(color.info.guest_address)', raster)
        self.assertIn('regs.depth_control.depth_enable', raster)
        self.assertIn('color.info.size.width == config.width', raster)
        self.assertIn('depth.info.size.height == config.height', raster)
        self.assertEqual(raster.count("const bool eligible_native_scene ="), 2)
        self.assertIn("db_desc.first == camera_motion->Depth() || eligible_native_scene", raster)

    def test_reprojected_history_remains_live_and_rejected_locally(self):
        self.assertIn("Gow3NativePatchError(InputPos, ivec2(0))", UPSCALE)
        self.assertIn("Gow3NativePatchError(InputPos, modelOffset)", UPSCALE)
        self.assertIn("bestError < 0.002", UPSCALE)
        self.assertIn("invalidReprojection = true;", UPSCALE)
        self.assertIn("SampleHistoryCatmullRom(PrevUV)", UPSCALE)
        self.assertIn("Upsampledcw.xyz = mix(HistoryColor, Upsampledcw.xyz, alpha);", UPSCALE)
        self.assertIn("imageStore(HistoryOutput", UPSCALE)


if __name__ == "__main__":
    unittest.main()
