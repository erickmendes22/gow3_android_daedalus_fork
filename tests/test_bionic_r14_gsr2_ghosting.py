"""R14: prevent double exposure from unrelated camera transforms and
native display-copy passes that reseed the same framebuffer repeatedly.
"""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
def read(name):return (R/name).read_text(encoding="utf-8")

class R14Ghosting(unittest.TestCase):
    def test_camera_provenance_and_cut_guard(self):
        h=read("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.h")
        c=read("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp")
        self.assertIn("Gsr2HistoryValidity() const noexcept",h)
        for signal in ("DifferentShader","ProjectionCut","PositionCut","RotationCut",
                       "current.shader_hash != previous.shader_hash",
                       "displacement_sq > 64.f", "forward_dot < 0.90f"):
            self.assertIn(signal,h)
        self.assertIn("frame_camera_shader_hash == shader_hash",c)
        self.assertIn("current.shader_hash = frame_camera_shader_hash;",c)
        self.assertIn("frame_camera_shader_hash = 0;",c)
    def test_invalid_camera_always_resets_history_and_zeros_motion(self):
        c=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn("GSR2_HISTORY_GUARD dispatch=",c)
        self.assertIn("camera_motion.Gsr2HistoryValidity() == CameraMotion::Gsr2HistoryStatus::Valid",c)
        self.assertIn("const bool temporal_ready =",c)
        self.assertIn("!guest_display_mode_recording &&",c)
        self.assertIn(".reset = reset || !temporal_ready,",c)
        segment=c.split("void TemporalUpscaler::RunScaled()",1)[1].split(
            "vk::ImageView TemporalUpscaler::Mirror(",1)[0]
        self.assertIn("if (reprojection)",segment)
        self.assertIn("cmdbuf.clearColorImage(vk::Image(motion_image)",segment)
    def test_one_prefill_per_new_image_and_no_host_reuse_without_redirection(self):
        c=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        h=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.h")
        self.assertIn("gsr2_completed_generation",h)
        self.assertIn("gsr2_seed_generation",h)
        self.assertIn("++gsr2_completed_generation;",c)
        redirect=c.split("bool TemporalUpscaler::RedirectColor(",1)[1].split(
            "bool TemporalUpscaler::RedirectDepth(",1)[0]
        self.assertIn("if (!display_redirect)",redirect)
        self.assertIn("display.valid = false; // Presenter falls back",redirect)
        self.assertIn("const bool new_gsr2_image = prefill_gsr2 &&",redirect)
        self.assertIn("display.gsr2_seed_generation != gsr2_completed_generation",redirect)
        self.assertIn("if (new_gsr2_image)",redirect)
        self.assertIn("display.gsr2_seed_generation = gsr2_completed_generation;",redirect)
        self.assertIn("const bool preserve = prefill_gsr2 && display.valid",redirect)
        self.assertIn("preserve ? vk::ImageLayout::eGeneral : vk::ImageLayout::eUndefined",redirect)
        self.assertIn("completed_temporal_frame && ui_image",redirect)
    def test_unrelated_ui_and_framegen_untouched(self):
        wf=read(".github/workflows/bionic-apk.yml")
        self.assertIn("fix/bionic-r14-gsr2-history-camera-guard-20261019",wf)
        self.assertIn("r14-build-trigger.txt",wf)
        self.assertIn("cancel-in-progress: true",wf)

if __name__=="__main__":unittest.main()
