"""ZIP (11): distinguish first display copy from finished combat/3D scene.

Actual one-flip snapshots show: draws 1-28 byte-identical; effects enter at
29 and continue to 80; next draw after 80 has depth disabled. The capture
must happen at a GPU state transition BEFORE the depthless guest draw, not
at a fixed draw index or after the HUD. This is a source contract, not proof
of on-device image quality.
"""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VK=ROOT/"gpu/shadps4/video_core/renderer_vulkan"
R=(VK/"vk_rasterizer.cpp").read_text()
RH=(VK/"vk_rasterizer.h").read_text()
U=(VK/"vk_temporal_upscaler.cpp").read_text()
UH=(VK/"vk_temporal_upscaler.h").read_text()
JAVA=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()

class Finished3DSource(unittest.TestCase):
    def test_dynamic_scene_to_ui_boundary_not_magic_draw_number(self):
        self.assertIn("gsr2_stage_last_depth_enabled && !next_has_depth",R)
        self.assertIn("!gsr2_stage_full_scene_captured && completed >= 32",R)
        self.assertIn("CaptureGsr2BeforeDepthlessPass(address, cb_descs[0].first, completed)",R)
        self.assertIn("gsr2_stage_last_depth_enabled = next_has_depth;",R)
        self.assertIn("bool gsr2_stage_full_scene_captured = false;",RH)
        self.assertIn("gsr2_stage_full_scene_captured = false;",R)

    def test_copy_is_recorded_before_depthless_draw(self):
        start=R.index("void Rasterizer::DrawRecord(")
        end=R.index("const auto state = BeginRendering(pipeline);",start)
        hook=R.index("upscaler->CaptureGsr2BeforeDepthlessPass",start)
        self.assertLess(hook,end)
        self.assertIn("scheduler.EndRendering();",U.split(
            "void TemporalUpscaler::CaptureGsr2BeforeDepthlessPass(",1)[1].split(
            "void TemporalUpscaler::ProbeGsr2VideoOutStage(",1)[0])
        self.assertIn("vk::ImageLayout::eGeneral",U)
        self.assertIn("cmd.copyImage(color.GetImage()",U)

    def test_same_guest_and_frame_and_safely_reuse_early_image(self):
        section=U.split("void TemporalUpscaler::CaptureGsr2BeforeDepthlessPass(",1)[1].split(
            "void TemporalUpscaler::ProbeGsr2VideoOutStage(",1)[0]
        self.assertIn("s.guest == guest && s.captured",section)
        self.assertIn("!slot->post_scene_valid",section)
        self.assertIn("color.info.guest_address != guest",section)
        self.assertIn("color.info.pixel_format != slot->post_scene_format",section)
        self.assertIn("slot->post_scene_final_valid = true;",section)
        self.assertIn("slot->post_scene_completed_draws = completed_draws;",section)
        self.assertIn("slot->post_scene_final_valid = false;",U)
        self.assertIn('"finished_3d_before_depthless_temporal"',U)
        self.assertIn('"early_display_copy_temporal"',U)
        self.assertIn("finished_3d=%d after_draw=%u",U)
        self.assertIn("fNNN_post_scene_WxH_",JAVA)

if __name__ == "__main__":
    unittest.main()
