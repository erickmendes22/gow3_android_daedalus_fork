"""Regression for one-flip, user-armed GoW III GSR2 VideoOut stage scan.

Checks the instrumented code path, not visual quality on a phone.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
GPU=ROOT/"gpu/shadps4/video_core/renderer_vulkan"
R=(GPU/"vk_rasterizer.cpp").read_text()
U=(GPU/"vk_temporal_upscaler.cpp").read_text()
H=(GPU/"vk_temporal_upscaler.h").read_text()
JAVA=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
SHELL=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()

class RenderStageScan(unittest.TestCase):
    def test_actual_draw_boundaries_and_explicit_trigger(self):
        self.assertIn("CaptureGsr2AfterVideoOutCopy(address, cb_descs[0].first)",R)
        self.assertIn("ProbeGsr2VideoOutStage(",R)
        self.assertIn("FinishGsr2VideoOutStageScan(guest_address)",R)
        self.assertIn("static constexpr std::array<u32, 12> stage_draws",U)
        self.assertIn("1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048",U)
        self.assertIn("if (!gsr2_stage_scan_armed || !guest || !target) return;",U)
        self.assertIn('std::getenv("GOW3_GSR2_STAGE_TRIGGER")',U)
        self.assertIn("gsr2_stage_scan_armed = true;",U)
        self.assertIn("gsr2_stage_scan_armed = false;",U)

    def test_images_are_from_actual_guest_and_exact_flip(self):
        self.assertIn("color.info.guest_address != guest",U)
        self.assertIn("FrameCapture::IsDisplayBuffer(guest)",U)
        self.assertIn("runtime.Transit(&color,vk::ImageLayout::eGeneral",U)
        self.assertIn("DumpImages(instance,scheduler,scheduler.CommandBuffer(),0,",U)
        self.assertIn('scan_%03u_guest_%llx_after_draw_%04u',U)
        self.assertIn("gsr2_stage_scan_final_guest = presented_guest;",U)
        self.assertIn("gsr2_stage_scan_final_guest == source.info.guest_address",U)
        self.assertIn("GSR2_STAGE_SCAN_FINISH actual_flip_guest=",U)
        self.assertIn("GSR2_STAGE_SCAN_FINAL guest=",U)

    def test_menu_and_export_are_explicit_and_separate_from_normal_capture(self):
        self.assertIn("void startGsr2RenderStages()",JAVA)
        self.assertIn("Capture GSR2 render stages",JAVA)
        self.assertIn('new File(BASE,"gsr2-stages.trigger")',JAVA)
        self.assertIn('new File(BASE,"gsr2-capture.trigger").delete()',JAVA)
        self.assertIn('export GOW3_GSR2_STAGE_TRIGGER="$base/gsr2-stages.trigger"',SHELL)
        self.assertIn("f000_scan_actual_flip_guest_",JAVA)
        self.assertIn("GSR2_STAGE_SCAN_FINISH",JAVA)
        self.assertIn("GSR2_STAGE_SCAN_SAMPLE",U)

    def test_input_to_gsr2_untouched_by_instrumentation(self):
        self.assertIn("RecordGsr2(cmd, source_view, chosen_depth_view, w, h, ow, oh)",U)
        self.assertIn("const vk::ImageView source_view = post_scene",U)
        self.assertIn("bool pre_hud_recording = false;",H)
        self.assertIn("VAddr gsr2_stage_scan_final_guest = 0;",H)

if __name__=="__main__":
    unittest.main()
