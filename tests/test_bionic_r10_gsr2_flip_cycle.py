"""R10 precise display lifetime regression: never cancel a valid GSR2 flip
from an intervening RGBA8 pass. Sample all three GoW3 video flip addresses."""
import unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def source(p):return (R/p).read_text(encoding="utf-8")
class Gsr2R10(unittest.TestCase):
    def test_intermediate_scene_color_does_not_cancel_display(self):
        s=source("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        part=s.split("void TemporalUpscaler::OnColorTarget(",1)[1].split(
            "void TemporalUpscaler::OnDisplayBoundary(",1)[0]
        self.assertIn("ldr_target = color;",part)
        self.assertNotIn("display_redirect = false;",part)
        begin=s.split("bool TemporalUpscaler::OnFrameStart()",1)[1].split(
            "void TemporalUpscaler::OnDispatch(",1)[0]
        self.assertIn("display_redirect = ui_phase;",begin)
        self.assertIn("display_redirect",source("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.h"))
    def test_samples_all_three_rotating_present_buffers(self):
        p=source("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
        u=source("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn("requests % 1200 <= 2",p)
        self.assertIn("queries % 1200 <= 2",u)
        self.assertIn("GSR2_DISPLAY_PUBLISH guest=",u)
        self.assertIn("GSR2_PRESENT_QUERY guest=",u)
        self.assertIn("GSR2_PRESENTER actual_guest=",p)
    def test_gsr2_only_existing_correctness_guards(self):
        code=source("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn("const bool prefill_gsr2 = UseGsr2()",code)
        self.assertIn("const bool new_gsr2_image = prefill_gsr2",code)
        self.assertIn("GSR2_PRESENT_INIT copied full UI",code)
        ci=source(".github/workflows/bionic-apk.yml")
        self.assertIn("r14-build-trigger.txt",ci)
        self.assertIn("fix/bionic-r14-gsr2-history-camera-guard-20261019",ci)
        self.assertIn("cancel-in-progress: true",ci)
if __name__=="__main__":unittest.main()
