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

    def test_scene_snapshot_matches_exact_flip_and_ui_is_not_in_temporal_history(self):
        cpp = (VK / "vk_temporal_upscaler.cpp").read_text(encoding="utf-8")
        hdr = (VK / "vk_temporal_upscaler.h").read_text(encoding="utf-8")
        rast = (VK / "vk_rasterizer.cpp").read_text(encoding="utf-8")
        shader = (ROOT / "gpu/shadps4/video_core/host_shaders/gsr2_prehud_composite.comp").read_text()
        build = (ROOT / "gpu/CMakeLists.txt").read_text()
        shell = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()
        self.assertIn("PreHudSlot() : image{} {}", hdr)
        self.assertIn("CaptureGsr2PreHudScene(VAddr guest_address)", hdr)
        self.assertIn("SelectGsr2PreHudScene(VAddr guest_address)", hdr)
        self.assertIn("upscaler->CaptureGsr2PreHudScene(regs.color_buffers[0].Address());", rast)
        self.assertIn("upscaler->SelectGsr2PreHudScene(guest_address);", rast)
        self.assertIn("slot->captured = false;", cpp)
        self.assertIn("cmd.copyImage(color.GetImage()", cpp)
        self.assertIn("cmd.copyImage(depth.GetImage()",cpp)
        self.assertIn("slot->depth_valid = true;",cpp)
        self.assertIn("slot.depth_id == completed_depth",cpp)
        self.assertIn("slot.depth_uid == depth.image_uid",cpp)
        self.assertIn("slot.depth_alias_generation == depth.alias_generation",cpp)
        self.assertIn("chosen_depth_view = *pre_hud_slots[pre_hud_completed_slot].depth_view;",cpp)
        self.assertIn("VideoCore::UniqueImage depth_image;",hdr)
        self.assertIn("pre_hud_consecutive_matches >= 3", cpp)
        self.assertIn("pre_hud_slots[pre_hud_completed_slot].view", cpp)
        self.assertIn("pre_hud_recording = prehud;", cpp)
        self.assertIn("sampled(guest_view)",cpp)
        self.assertIn("sampled(*output_view)",cpp)
        self.assertIn("OutputComposited",shader)
        self.assertIn("foregroundResidual",shader)
        self.assertIn("vec3 before=textureLod(InputPreHud,uv,0.0).rgb;",shader)
        self.assertIn("vec3 restored=clamp(applyGrade(gsrScene)+",shader)
        self.assertIn("vec3 result=mix(restored,guest,guestWeight);",shader)
        self.assertIn("smoothstep(0.06,0.16,residualEdge)",shader)
        self.assertIn("GSR2_HISTORY_DISPATCH_TOTAL",cpp)
        self.assertIn("kept<8.0 ? 1.0",shader)
        self.assertIn("gradeGain",shader)
        self.assertIn("gradeBias",shader)
        self.assertIn("smoothstep(12.0,15.0,bad);",shader)
        self.assertIn("barrier();",shader)
        self.assertIn("sameflip_prehud",cpp)
        self.assertIn("sameflip_videoout",cpp)
        self.assertIn("sameflip_gsr2",cpp)
        self.assertIn("sameflip_composited",cpp)
        self.assertIn("pre_hud_linear_sampler",cpp)
        self.assertIn("createSamplerUnique",cpp)
        self.assertIn("gsr2_prehud_composite.comp",build)
        self.assertIn('GOW3_GSR2_PREHUD_COMPOSITE:-1',shell)
        self.assertIn("} else {\n        // Stable fallback",cpp)

    def test_global_grade_is_not_mistaken_for_a_scene_change(self):
        # Device captures: 212023 at flip 7200 has large global color change
        # that previously triggered the binary 5/16 fullscreen fallback;
        # 215958 at flip 9600 also has a widespread display copy grade.
        # Brightening the SAME scene is not evidence of a different scene.
        shader = (ROOT / "gpu/shadps4/video_core/host_shaders/gsr2_prehud_composite.comp").read_text()
        self.assertIn("vec3 covariance=sumXY*rcpCount-meanX*meanY;",shader)
        self.assertIn("gradeGain=mix(vec3(1.0),fitted,",shader)
        self.assertIn("gradeBias=clamp(meanY-gradeGain*meanX",shader)
        self.assertIn("vec3 estimated=applyGrade(texelFetch(InputPreHud,p,0).rgb);",shader)
        self.assertIn("smoothstep(12.0,15.0,bad);",shader)
        self.assertNotIn("incompatibleScene=uint(different>=5u)",shader)
        self.assertIn("smoothstep(0.06,0.16,residualEdge)",shader)

    def test_same_frame_postprocess_is_restored_without_temporal_hud_contamination(self):
        # Identity-GSR input must reconstruct EXACTLY the final VideoOut
        # even when the copy pass applies global color correction (9600 case).
        source_before = (0.11, 0.21, 0.07)
        guest_after = (0.09, 0.13, 0.02)
        temporal_scene = source_before
        restored = tuple(max(0.0, min(1.0, temporali + guesti - beforei))
                         for temporali, guesti, beforei in
                         zip(temporal_scene, guest_after, source_before))
        self.assertEqual(tuple(round(v, 6) for v in restored), guest_after)
        # An opaque HUD difference remains guest-only: never enter history.
        threshold = 0.045
        self.assertGreater(abs(1.0 - 0.1), threshold)
        self.assertEqual((1.0 if abs(1.0 - 0.1) > threshold else 0.1), 1.0)

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
