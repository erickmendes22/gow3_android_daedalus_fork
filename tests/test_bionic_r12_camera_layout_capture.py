"""R12 captures only verified guest vertex-constant bytes to map
CUSA01623 shader parameters without inventing a camera transform.
"""
import unittest
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
def get(name):return (BASE/name).read_text(encoding="utf-8")
class R12(unittest.TestCase):
    def test_source_shader_identity_and_host_copy(self):
        raster=get("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        camera=get("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp")
        header=get("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.h")
        self.assertIn("void OnConstants(const float* data, size_t float_count, u64 shader_hash, u32 buffer_slot);",header)
        self.assertIn("void CameraMotion::OnConstants(const float* data, size_t float_count, u64 shader_hash, u32 buffer_slot)",camera)
        self.assertEqual(raster.count("stage.pgm_hash, buffer_index);"),2)
        self.assertIn("constant_ring->Data(ring->offset)",raster)
    def test_bounded_late_gameplay_capture(self):
        camera=get("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp")
        self.assertIn("frame_number == 1200 || frame_number == 3600",camera)
        self.assertIn("probe_seen < 1024",camera)
        self.assertIn("probe_written < 32",camera)
        self.assertIn("probe_seen <= 8 || probe_seen % 32 == 0",camera)
        self.assertIn("std::min(float_count, size_t(512))",camera)
        self.assertIn("GSR2_CAMERA_RAW frame=%u sample=%u shader=%016llx slot=%u",camera)
        self.assertIn("std::bit_cast<u32>(data[start + i])",camera)
        self.assertIn("start += 128",camera)
        self.assertIn("offset=%zu count=%zu hex=%s",camera)
        self.assertIn("std::fflush(stdout);",camera)
    def test_do_not_fake_temporal_matrices(self):
        camera=get("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp")
        self.assertIn("frame_pose_votes >= 2",camera)
        self.assertIn("GOW3_CAMERA_VERIFIED",camera)
        u=get("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn(".reset = reset || !temporal_ready,",u)
        self.assertIn("spatial-reset-no-history",u)
    def test_trigger_restricted_to_this_branch(self):
        w=get(".github/workflows/bionic-apk.yml")
        self.assertIn("r14-build-trigger.txt",w)
        self.assertIn("fix/bionic-r14-gsr2-history-camera-guard-20261019",w)
        self.assertIn("cancel-in-progress: true",w)
if __name__=="__main__":unittest.main()
