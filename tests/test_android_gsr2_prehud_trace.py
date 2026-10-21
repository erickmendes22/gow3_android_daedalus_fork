"""Check that pre-HUD probing never substitutes its unverified image for VideoOut."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu/shadps4/video_core/renderer_vulkan"

class TestGsr2PreHudTrace(unittest.TestCase):
    def test_pre_hud_probe_is_tied_to_first_display_target_draw(self):
        rast = (VK / "vk_rasterizer.cpp").read_text(encoding="utf-8")
        self.assertIn("camera_motion->OnDisplayTargetDraw(regs.color_buffers[0].Address());", rast)
        self.assertIn("upscaler->ProbeGsr2PreHudSource(regs.color_buffers[0].Address());", rast)
        self.assertLess(
            rast.index("camera_motion->OnDisplayTargetDraw(regs.color_buffers[0].Address());"),
            rast.index("upscaler->ProbeGsr2PreHudSource(regs.color_buffers[0].Address());"),
        )

    def test_probe_is_opt_in_and_does_not_redirect_output(self):
        cpp = (VK / "vk_temporal_upscaler.cpp").read_text(encoding="utf-8")
        hdr = (VK / "vk_temporal_upscaler.h").read_text(encoding="utf-8")
        self.assertIn("void ProbeGsr2PreHudSource(VAddr guest_address);", hdr)
        body = cpp.split("void TemporalUpscaler::ProbeGsr2PreHudSource(", 1)[1].split(
            "namespace {", 1)[0]
        self.assertIn("GOW3_GSR2_AUTO_PROBE", body)
        self.assertIn("GSR2_PREHUD_CANDIDATE", body)
        self.assertIn("!FrameCapture::IsDisplayBuffer(color.info.guest_address)", body)
        self.assertIn("depth_extent", body)
        self.assertIn("pre_hud_candidate", body)
        self.assertNotIn("RecordGsr2(", body)
        self.assertNotIn("ui_phase = true", body)
        self.assertNotIn("display_redirect = true", body)

    def test_direct_videoout_does_not_overwrite_last_scene_ldr(self):
        cpp = (VK / "vk_temporal_upscaler.cpp").read_text(encoding="utf-8")
        section = cpp.split("void TemporalUpscaler::OnColorTarget(", 1)[1].split(
            "void TemporalUpscaler::OnDisplayBoundary(", 1)[0]
        self.assertIn("if (Gsr2GuestDisplayMode() &&", section)
        self.assertIn("FrameCapture::IsDisplayBuffer(image.info.guest_address)", section)
        self.assertLess(section.index("FrameCapture::IsDisplayBuffer("),
                        section.index("ldr_target = color;"))
        # The identified source is only retained for scene provenance; the
        # stable direct-VideoOut renderer still reads the real guest output.
        present = cpp.split("bool TemporalUpscaler::PresentGsr2FromGuestDisplay(", 1)[1].split(
            "bool TemporalUpscaler::DisplayOverride(", 1)[0]
        self.assertIn("auto& source = texture_cache.GetImage(guest);", present)
        self.assertIn("RecordGsr2(cmd, source_view, chosen_depth_view, w, h, ow, oh)", present)

    def test_reject_non_finite_scene_projection(self):
        cpp = (VK / "vk_temporal_upscaler.cpp").read_text(encoding="utf-8")
        section = cpp.split("bool TemporalUpscaler::PresentGsr2FromGuestDisplay(", 1)[1].split(
            "bool TemporalUpscaler::DisplayOverride(", 1)[0]
        self.assertIn("std::isfinite(fov)", section)
        self.assertIn("GSR2_SCENE_PROJECTION_REJECT", section)
        self.assertLess(section.index("GSR2_SCENE_PROJECTION_REJECT"),
                        section.index("camera_motion.RecordCompletedMotion("))

if __name__ == "__main__":
    unittest.main()
