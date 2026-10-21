"""A direct GSR2 flip must reject a depth attachment rewritten after capture."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / "gpu/shadps4/video_core/texture_cache"

class DepthWriteGeneration(unittest.TestCase):
    def test_depth_write_flag_follows_depth_control(self):
        src = (TEX / "texture_cache.h").read_text()
        self.assertIn("bool depth_write{false};", src)
        self.assertIn("depth_write{bool(ctl.depth_write_enable)}", src)

    def test_publish_gsr2_write_provenance_only_for_writable_depth(self):
        src = (TEX / "texture_cache.cpp").read_text()
        block = src.split("ImageView& TextureCache::FindDepthTarget(", 1)[1].split(
            "void TextureCache::RefreshImage(", 1)[0]
        self.assertIn('std::getenv("GOW3_ANDROID_PORT")', block)
        self.assertIn('std::getenv("GOW3_GSR2_DIRECT_VIDEOOUT")', block)
        self.assertIn("if (track_gsr2_depth_writes && desc.depth_write)", block)
        self.assertIn("PublishAliasWrite(image_id);", block)
        self.assertLess(block.index("UpdateImage(image_id);"),
                        block.index("PublishAliasWrite(image_id);"))

    def test_flip_rejects_generation_that_changed_since_capture(self):
        src = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp").read_text()
        capture = src.split("void CameraMotion::OnDisplayTargetDraw(",1)[1].split(
            "void CameraMotion::OnDisplayPass(",1)[0]
        verify = src.split("void CameraMotion::OnDisplayPass(",1)[1].split(
            "void CameraMotion::Overlay(",1)[0]
        self.assertIn("candidate.depth_alias_generation = depth_image.alias_generation;", capture)
        self.assertIn("depth_image->alias_generation != candidate.depth_alias_generation", verify)
        self.assertIn("depth_id = {};", verify)

if __name__ == "__main__":
    unittest.main()
