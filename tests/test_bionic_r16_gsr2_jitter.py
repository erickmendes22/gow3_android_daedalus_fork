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
        self.assertIn(".jitter = {sign * jitter[0], sign * jitter[1]},",fn)
        self.assertNotIn(".jitter = temporal_ready ?",fn)
        self.assertIn(".reset = reset || !temporal_ready,",fn)
        self.assertIn("const bool temporal_ready = temporal_status ==",fn)
        self.assertIn("std::getenv(\"GOW3_ANDROID_PORT\")",source)
        self.assertIn("const bool jitter_on = active && settings.jitter",source)
    def test_invalid_motion_is_cleared_before_gsr2_dispatch(self):
        source=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        run=source.split("void TemporalUpscaler::RunScaled()",1)[1].split(
            "vk::ImageView TemporalUpscaler::Mirror(",1)[0]
        self.assertIn("if (reprojection)",run)
        self.assertIn("cmdbuf.clearColorImage(vk::Image(motion_image)",run)

if __name__ == "__main__":
    unittest.main()
