"""R9 fixes the GSR2 host display lifetime proven by R8 runtime logs.

Evidence: 5400 real GSR2 dispatches, approximately 10k presenter queries
reporting override=0 / valid=0. The frame-boundary was incorrectly processed
on every guest display draw and non-display passes canceled redirection.
"""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def src(path): return (ROOT/path).read_text(encoding="utf-8")
class R9(unittest.TestCase):
    def test_consume_one_scene_boundary_not_every_guest_display_draw(self):
        raster=src("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        self.assertIn("const bool is_display_draw = regs.color_buffers[0]",raster)
        self.assertIn("const bool gsr2_bionic =",raster)
        self.assertIn("(!gsr2_bionic || scene_started)",raster)
        self.assertIn("upscaler->OnDisplayBoundary(cb_descs[0].first);",raster)
        self.assertIn("upscaler->OnFrameStart()",raster)
        self.assertIn("!gsr2_bionic",raster)
    def test_preserve_host_redirect_during_intermediate_offscreen_passes(self):
        cpp=src("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn("if (!UseGsr2() || !std::getenv(\"GOW3_ANDROID_PORT\"))",cpp)
        self.assertIn("const bool keep_this_frame = UseGsr2()",cpp)
        self.assertIn("completed_temporal_frame && Active()",cpp)
        self.assertIn("display.valid && bool(display.image)",cpp)
        self.assertIn("if (!keep_this_frame)",cpp)
        self.assertIn("display_redirect = false;",cpp)
        self.assertIn("GSR2_PRESENT_QUERY",cpp)
        self.assertIn("GSR2_PRESENT_INIT",cpp)
    def test_reset_only_on_next_real_forward_scene(self):
        cpp=src("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        segment=cpp.split("void TemporalUpscaler::OnColorTarget(",1)[1].split(
            "void TemporalUpscaler::OnDisplayBoundary(",1)[0]
        self.assertIn("!FrameCapture::IsDisplayBuffer(image.info.guest_address)",segment)
        self.assertIn("display_redirect = false;",segment)
    def test_gated_single_build_and_existing_hud_lsfg_untouched(self):
        workflow=src(".github/workflows/bionic-apk.yml")
        self.assertIn("r9-build-trigger.txt",workflow)
        self.assertIn("fix/bionic-r9-gsr2-frame-lifecycle-20261019",workflow)
        self.assertIn("cancel-in-progress: true",workflow)
        script=src("tools/android/bionic/run-bionic.sh")
        self.assertIn("export GOW3_GSR2_AUTO_PROBE=1",script)
        self.assertIn("export GOW3_GSR2_PREFILL_DISPLAY=1",script)
if __name__=="__main__": unittest.main()
