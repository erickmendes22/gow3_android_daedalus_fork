"""GSR2 Native AA must consume the same image as non-GSR2 VideoOut.

Static source contract before a full Bionic Vulkan build. Does not claim
that visual output or GPU synchronization has been validated on a device.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
def src(path):
    return (ROOT / path).read_text(encoding="utf-8")

PRESENTER = src("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
UPSCALE = src("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
HEADER = src("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.h")

class VideoOutGsr2Input(unittest.TestCase):
    def test_source_is_presenters_real_guest_image_not_pre_display_cb(self):
        first = PRESENTER.index("image_id = texture_cache.FindImage(desc);", PRESENTER.index("Frame* Presenter::PrepareFrame("))
        update = PRESENTER.index("texture_cache.UpdateImage(image_id);", first)
        acquire = PRESENTER.index("PresentGsr2FromGuestDisplay(image_id, display);", update)
        self.assertLess(first, update)
        self.assertLess(update, acquire)
        self.assertIn("bool upscaled = rasterizer->GetUpscaler().DisplayOverride(", PRESENTER)
        self.assertIn("if (!upscaled) {", PRESENTER[:first])
        self.assertIn("if (Gsr2GuestDisplayMode()) return;", UPSCALE)
        self.assertIn("if (Gsr2GuestDisplayMode()) return false;", UPSCALE)

    def test_verified_real_guest_raster_and_safe_fallback(self):
        self.assertIn("Gow3Settings::RenderPreset() == Gow3Settings::NativeAA ||", UPSCALE)
        self.assertIn("if (!Gsr2GuestDisplayMode() || !Active() || !guest) return false;", UPSCALE)
        self.assertIn("FrameCapture::IsDisplayBuffer(source.info.guest_address) == false", UPSCALE)
        self.assertIn('std::getenv("GOW3_GSR2_DIRECT_VIDEOOUT")', UPSCALE)
        self.assertIn('std::getenv("GOW3_GSR2_INPUT_RES")', UPSCALE)
        self.assertIn('w != expected_w || h != expected_h', UPSCALE)
        self.assertIn('scene_targets.SetSize(scene_targets.GuestSize());', UPSCALE)
        self.assertIn('RecordGsr2(cmd, source_view, *guest_display_depth_view, w, h, ow, oh)', UPSCALE)
        self.assertIn('GSR2_VIDEOOUT_SOURCE verified_guest=', UPSCALE)

        self.assertIn("if (!EnsureResources(w, h, ow, oh, false)) return false;", UPSCALE)
        self.assertIn("if (!ok) return false;", UPSCALE)
        self.assertIn("guest_display_mode_recording = true;", UPSCALE)
        self.assertIn("guest_display_mode_recording = false;", UPSCALE)
        self.assertIn("!guest_display_mode_recording &&", UPSCALE)
        self.assertIn("display = {vk::Image(ui_image), source.info.pixel_format, ow, oh};", UPSCALE)
        self.assertIn("bool PresentGsr2FromGuestDisplay(VideoCore::ImageId guest, Display& display);", HEADER)

    def test_no_guessed_depth_or_motion_for_final_ui_image(self):
        self.assertIn(".format = vk::Format::eR32Sfloat", UPSCALE)
        self.assertIn("vk::ImageUsageFlagBits::eSampled | vk::ImageUsageFlagBits::eTransferDst", UPSCALE)
        self.assertIn("vk::Image(guest_display_depth)", UPSCALE)
        self.assertIn("vk::Image(motion_image)", UPSCALE)
        self.assertIn("guest_display_mode_recording", HEADER)
        self.assertIn("GSR2_VIDEOOUT_SOURCE verified_guest=", UPSCALE)

    def test_zero_motion_clear_has_required_vulkan_usage(self):
        creation = UPSCALE[UPSCALE.index("motion_image.Create(vk::ImageCreateInfo{"): UPSCALE.index("output_image = VideoCore::UniqueImage")]
        self.assertIn("vk::ImageUsageFlagBits::eTransferDst", creation)
        self.assertIn("clearColorImage(vk::Image(motion_image)", UPSCALE)
        self.assertIn('"videoout_original"', UPSCALE)
        self.assertIn('"videoout_gsr2"', UPSCALE)
        self.assertIn('"videoout_filtered"', UPSCALE)

if __name__ == "__main__":
    unittest.main()
