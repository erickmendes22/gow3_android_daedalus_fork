"""R16 regression: GSR2 must receive the jitter used when rasterizing the scene.

An invalid camera resets history and clears motion, but it does not mean that
rasterized geometry was drawn without a subpixel jitter. The input pixel grid
and the upscaler's declared jitter must continue to agree on spatial frames.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT/path).read_text(encoding="utf-8")

class R16Gsr2JitterConsistency(unittest.TestCase):
    def test_rasterizer_uses_upscaler_jitter(self):
        raster=read("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        self.assertIn("draw_jitter = upscaler->Jitter();", raster)
        self.assertIn("viewport.x = (xoffset - xscale) * target_scale[0] + draw_jitter[0]",raster)
        self.assertIn("viewport.y = (yoffset - yscale) * target_scale[1] + draw_jitter[1]",raster)
    def test_gsr2_receives_same_jitter_in_spatial_mode(self):
        source=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        fn=source.split("bool TemporalUpscaler::RecordGsr2(",1)[1].split(
            "bool TemporalUpscaler::UseDlss()",1)[0]
        # The VideoOut dispatch happens after OnFrameStart changes the phase:
        # never pass next-frame jitter (or constant zero) to GSR2.
        self.assertIn("? camera_motion.CompletedJitter() : jitter;", fn)
        self.assertIn(".jitter = {sign * frame_jitter[0], sign * frame_jitter[1]},", fn)
        self.assertNotIn(".jitter = guest_display_mode_recording", fn)
        self.assertIn("GSR2_TEMPORAL_INPUT frame=", fn)
        self.assertNotIn(".jitter = temporal_ready ?",fn)
        self.assertIn("const bool dispatch_reset =",fn)
        self.assertIn("!temporal_ready;",fn)
        self.assertIn(".reset = dispatch_reset,",fn)
        self.assertIn("const bool temporal_ready =",fn)
        self.assertIn("(!guest_display_mode_recording || guest_display_motion_ready)",fn)
        self.assertIn("std::getenv(\"GOW3_ANDROID_PORT\")",source)
        self.assertIn('std::getenv("GOW3_GSR2_TEMPORAL_JITTER")', source)
        self.assertIn("preset != Gow3Settings::NativeAA", source)
        self.assertIn("(!Gsr2GuestDisplayMode() || direct_temporal)", source)
        cam=read("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp")
        hdr=read("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.h")
        self.assertIn("completed_current_jitter = jitter;", cam)
        self.assertIn("completed_previous_jitter = previous_jitter;", cam)
        self.assertIn("completed_current_jitter, completed_previous_jitter, false", cam)
        self.assertIn("std::array<float, 2> CompletedJitter() const noexcept", hdr)
        launch=read("tools/android/bionic/run-bionic.sh")
        self.assertIn('export GOW3_GSR2_TEMPORAL_JITTER=', launch)
    def test_invalid_motion_is_cleared_before_gsr2_dispatch(self):
        source=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        run=source.split("void TemporalUpscaler::RunScaled()",1)[1].split(
            "vk::ImageView TemporalUpscaler::Mirror(",1)[0]
        self.assertIn("if (reprojection)",run)
        self.assertIn("cmdbuf.clearColorImage(vk::Image(motion_image)",run)

if __name__ == "__main__":
    unittest.main()
