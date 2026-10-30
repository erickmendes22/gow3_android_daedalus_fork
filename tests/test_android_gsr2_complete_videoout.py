"""Regression: CUSA01623 GSR2 source must include animated actors and the exact depth."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
GPU=ROOT/"gpu/shadps4/video_core"
UPS=(GPU/"renderer_vulkan/vk_temporal_upscaler.cpp").read_text(encoding="utf-8")
SHADER=(GPU/"host_shaders/gsr2_prehud_composite.comp").read_text(encoding="utf-8")
APP=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text(encoding="utf-8")

class FullVideoOutRegression(unittest.TestCase):
    def test_full_color_selected_from_actual_videoout_not_old_ldr(self):
        self.assertIn('const bool force_early = prehud && std::getenv("GOW3_GSR2_USE_EARLY_PREHUD")',UPS)
        self.assertIn('const bool post_scene = prehud && !force_early &&',UPS)
        self.assertIn('const bool complete_videoout = prehud && !post_scene && !force_early',UPS)
        self.assertIn('const vk::ImageView source_view = post_scene',UPS)
        self.assertIn('GOW3_GSR2_FORCE_FULL_VIDEOOUT',UPS)
        self.assertIn('CaptureGsr2AfterVideoOutCopy(VAddr guest',UPS)
        self.assertIn('RecordGsr2(cmd, source_view, chosen_depth_view, w, h, ow, oh)',UPS)
        self.assertIn('camera_motion.RecordCompletedMotion(cmd, chosen_depth_view, *motion_view, w, h)',UPS)

    def test_srgb_is_encoded_at_output_and_old_compositor_is_retained_for_ab(self):
        self.assertIn('const vk::PushConstantRange push{vk::ShaderStageFlagBits::eCompute,0,28}',UPS)
        self.assertIn('static_assert(sizeof(Params)==28)',UPS)
        self.assertIn('u32 complete_videoout',UPS)
        self.assertIn('uint completeVideoOut;',SHADER)
        self.assertIn('if (params.completeVideoOut != 0u)',SHADER)
        self.assertIn('params.isSrgb!=0u ? encodeSrgb(scene) : clamp(scene,0.0,1.0)',SHADER)
        self.assertIn('float guestWeight=max(overlayWeight,guestFallbackWeight);',SHADER)

    def test_capture_records_both_actual_full_input_and_early_snapshot(self):
        self.assertIn('"early_prehud",fmt',UPS)
        self.assertIn('complete_videoout || !prehud ? source.GetImage()',UPS)
        self.assertIn('"post_scene",fmt',UPS)
        self.assertIn('post_scene ? "post_scene_copy_temporal"',UPS)
        self.assertIn('"full_videoout_temporal"',UPS)
        self.assertIn('full_color=%d temporal=%d',UPS)
        self.assertIn('fNNN_early_prehud_WxH_',APP)
        self.assertIn('HUD is not isolated',APP)

if __name__ == "__main__":
    unittest.main()
