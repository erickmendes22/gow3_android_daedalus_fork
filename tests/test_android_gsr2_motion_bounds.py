"""Regression for the camera-motion/SGSR2 offscreen history corruption.

Real GoW III diagnostics 2026-10-21 21:59 show valid temporal dispatches
but intermittent whole-screen corruption. A reprojection behind the camera
or outside the old raster must not silently read a CLAMP_TO_EDGE history
texel. Test shader safeguards without weakening motion on valid pixels.
"""
from pathlib import Path
import math
import unittest

ROOT=Path(__file__).resolve().parents[1]
SHADERS=ROOT / "gpu/shadps4/video_core/host_shaders"


def valid_motion(current, motion, size):
    if any(not math.isfinite(v) for v in motion):
        return False
    previous=[(current[i]+motion[i])/size[i] for i in range(2)]
    return all(abs(motion[i]) <= size[i] and
               0.0 <= previous[i] < 1.0 for i in range(2))


class MotionBounds(unittest.TestCase):
    def test_offscreen_and_nan_samples_always_reset_pixel_only(self):
        size=(640,360)
        self.assertTrue(valid_motion((250,140),(12,-3),size))
        self.assertFalse(valid_motion((2,140),(-12,0),size))
        self.assertFalse(valid_motion((639,140),(12,0),size))
        self.assertFalse(valid_motion((250,140),(1e8,0),size))
        self.assertFalse(valid_motion((250,140),(float("nan"),0),size))
        self.assertFalse(valid_motion((250,140),(float("inf"),0),size))

    def test_convert_rejects_motion_before_encoding(self):
        s=(SHADERS/"gsr2_convert.comp").read_text(encoding="utf-8")
        self.assertIn("vec2 historyUV = sceneUV + motionPixels * params.renderSizeRcp;",s)
        self.assertIn("any(lessThan(historyUV, vec2(0.0)))",s)
        self.assertIn("any(greaterThanEqual(historyUV, vec2(1.0)))",s)
        self.assertIn("any(isnan(motionPixels))",s)
        self.assertIn("any(isinf(motionPixels))",s)
        self.assertIn("motionPixels=vec2(0.0);",s)
        self.assertIn("depthclip=1.0;",s)
        self.assertIn("vec2 motion = -motionPixels * 2.0 * params.renderSizeRcp;",s)

    def test_upscale_no_longer_clamps_invalid_history_into_border_samples(self):
        s=(SHADERS/"gsr2_upscale.comp").read_text(encoding="utf-8")
        self.assertIn("vec2 rawPrevUV = -0.5 * Motion + Hruv;",s)
        self.assertIn("any(lessThan(rawPrevUV, vec2(0.0)))",s)
        self.assertIn("any(greaterThanEqual(rawPrevUV, vec2(1.0)))",s)
        self.assertIn("any(isnan(rawPrevUV))",s)
        self.assertIn("any(isinf(rawPrevUV))",s)
        self.assertIn("invalidReprojection ? 0.0",s)
        self.assertIn("isnan(Historyw) || isinf(Historyw)",s)
        self.assertIn("if (invalidReprojection) alpha=1.0;",s)
        self.assertIn("clamp(ivec2(Jitteruv * InputInfoViewportSize)",s)
        self.assertIn("ivec2(params.renderSize)-ivec2(1)",s)

    def test_valid_motion_stays_temporal(self):
        s=(SHADERS/"gsr2_upscale.comp").read_text(encoding="utf-8")
        self.assertIn("float rejectHistory=smoothstep",s)
        self.assertIn("alpha=max(alpha,rejectHistory);",s)
        self.assertIn("if (invalidReprojection) alpha=1.0;",s)
        self.assertIn("Upsampledcw.xyz = mix(HistoryColor, Upsampledcw.xyz, alpha);",s)
        self.assertIn("imageStore(HistoryOutput",s)


if __name__ == "__main__":
    unittest.main()
