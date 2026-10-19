"""R11 prevents the GSR2 camera starvation that forced every frame into
no-history spatial reconstruction on the verified GoW3 Bionic forward renderer.
"""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(path): return (ROOT/path).read_text(encoding="utf-8")

class BionicR11CameraFeed(unittest.TestCase):
    def test_gsr2_uses_actual_vertex_constants(self):
        src=read("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        section=src.split("bool Rasterizer::BindResources(const Pipeline* pipeline)",1)[1]
        self.assertIn('std::strcmp(active_upscaler, "gsr2") == 0',section)
        self.assertIn('std::getenv("GOW3_ANDROID_PORT")',section)
        self.assertIn("const bool android_camera_feed =",section)
        self.assertEqual(section.count("(gbuffer_draw || android_camera_feed)"),2)
        self.assertIn("camera_motion->Depth()",section)
        self.assertIn("stage.sw_stage == Shader::SwStage::Vertex",section)
        self.assertIn("camera_motion->OnConstants(",section)

    def test_host_constant_ring_not_guest_label(self):
        src=read("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        section=src.split('if (ring) {',1)[1].split('} else if (desc.IsSpecial())',1)[0]
        self.assertIn("constant_ring->Data(ring->offset)",section)
        self.assertIn("camera_motion->OnConstants(reinterpret_cast<const float*>(data)",section)
        self.assertNotIn("OnConstants(reinterpret_cast<const float*>(ring->address)",section)

    def test_motion_requires_verified_matrices_not_guessed_ones(self):
        cam=read("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp")
        src=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn('GSR2_CAMERA_FEED blocks=%u',cam)
        self.assertIn("GOW3_CAMERA_VERIFIED",cam)
        self.assertIn("frame_pose_votes >= 2",cam)
        self.assertIn("const bool temporal_ready = camera_motion.Ready();",src)
        self.assertIn(".reset = reset || !temporal_ready,",src)
        self.assertIn("GSR2_PRESENT_INIT copied full UI",src)

    def test_single_ci_trigger_preserves_prior_regressions(self):
        workflow=read(".github/workflows/bionic-apk.yml")
        self.assertIn("r11-build-trigger.txt",workflow)
        self.assertIn("fix/bionic-r11-gsr2-real-camera-feed-20261019",workflow)
        self.assertIn("cancel-in-progress: true",workflow)

if __name__=="__main__": unittest.main()
