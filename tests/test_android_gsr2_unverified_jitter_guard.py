"""Source contract: stabilize GoW III when framebuffer sampling does not follow requested Halton shifts.

Based on six actual same-flip GSR2 temporal captures in ZIP (6): measured
native image flow in stable geometry is < 0.04 input px per frame, yet the
recorded camera model gives several pixels of motion. This test verifies the
coherent source path; it does not claim visual correctness on a phone.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSCALE = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp").read_text()
RASTER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
GSR = (ROOT / "gpu/shadps4/video_core/host_shaders/gsr2_upscale.comp").read_text()

class Gsr2NativeRasterJitterGuard(unittest.TestCase):
    def test_unverified_subpixel_jitter_is_blocked_for_android_direct_videoout(self):
        self.assertIn("const bool verified_subpixel_jitter =", UPSCALE)
        self.assertIn('std::getenv("GOW3_GSR2_FORCE_UNVERIFIED_JITTER")', UPSCALE)
        self.assertIn("verified_subpixel_jitter &&", UPSCALE)
        self.assertIn("GSR2_RASTER_JITTER_GUARD", UPSCALE)
        self.assertIn("if (!jitter_on)", UPSCALE)
        self.assertIn("jitter = {};", UPSCALE)

    def test_scene_geometry_and_qualcomm_share_the_same_zero_jitter(self):
        self.assertIn("draw_jitter = upscaler->Jitter();", RASTER)
        self.assertIn("camera_motion->SetJitter(upscaler->Jitter());", RASTER)
        self.assertIn("pre_hud_recording ? camera_motion.CompletedJitter()", UPSCALE)
        self.assertIn(".jitter = spatial_only ? std::array<float,2>{0.0f,0.0f}", UPSCALE)
        self.assertIn("const bool dispatch_reset = spatial_only ||", UPSCALE)
        self.assertIn("vec2 InputJitter = params.jitterOffset;", GSR)

    def test_original_native_history_comparison_still_guards_camera_flow(self):
        self.assertIn("Gow3NativePatchError(InputPos, ivec2(0))", GSR)
        self.assertIn("Gow3NativePatchError(InputPos, modelOffset)", GSR)
        self.assertIn("invalidReprojection = true;", GSR)

if __name__ == "__main__":
    unittest.main()
