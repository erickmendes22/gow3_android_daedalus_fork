"""Regression for the actual residual GoW III GSR2 motion failure.

ZIP (12), 2026-10-30: six temporal frames with complete actor/effect color,
zero Halton jitter, and source matching the selected post-scene image. The
real previous-native background shifts ~(-1,+3) and (-1,+4) pixels, whereas
the original sparse 30-candidate search lacks BOTH diagonals.

A 5x3 search centered on the model's reasonably correct vertical motion
recovers the diagonals WITHOUT trusting the model's horizontally reversed
component. These tests do not claim on-device performance/visual proof.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHADER = (ROOT / "gpu/shadps4/video_core/host_shaders/gsr2_upscale.comp").read_text()
CPP = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp").read_text()
RASTER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()

class NativeYGuidedSearch(unittest.TestCase):
    def test_adaptive_search_uses_native_history_and_vertical_camera_only(self):
        body = SHADER.split("if (bestError > 0.00012 && modelWithinRange &&",1)[1].split(
            "if (bestError < 0.002)",1)[0]
        self.assertIn("abs(modelOffset.y) >= 2",body)
        self.assertIn("for (int y = -1; y <= 1; ++y)",body)
        self.assertIn("for (int x = -2; x <= 2; ++x)",body)
        self.assertIn("ivec2 candidate = ivec2(x, modelOffset.y + y)",body)
        self.assertNotIn("modelOffset.x + x",body)
        self.assertIn("Gow3NativeCenterLowerBound(InputPos, candidate)",body)
        self.assertIn("Gow3NativePatchError(InputPos, candidate)",body)
        self.assertIn("bestOffset = candidate",body)
        self.assertIn("bestError = cost",body)
        self.assertIn("Gow3NativePatchError(InputPos, bestOffset + ivec2(-1, 0))",SHADER)
        self.assertIn("PreviousNativeYCoCg, previous + taps[i]",SHADER)

    def test_ground_truth_minus_one_plus_four_was_missing(self):
        sparse = {(-4,0),(4,0),(0,-4),(0,4),(-2,-2),(-2,2),
                  (2,-2),(2,2),(-1,0),(1,0),(0,-1),(0,1),
                  (-1,-1),(-1,1),(1,-1),(1,1),(-3,0),(3,0),
                  (-3,-1),(-3,1),(3,-1),(3,1),(-2,-1),(-2,1),
                  (2,-1),(2,1),(-1,-2),(-1,2),(1,-2),(1,2)}
        self.assertEqual(len(sparse),30)
        true_offset=(-1,4)
        self.assertNotIn(true_offset,sparse)
        # Matches a perfectly shifted textured native prior, independent of
        # camera's wrong +X component. This is the exact five-tap geometry.
        prior=lambda x,y: ((x*73)^(y*41)^(x*y*19))&255
        taps=((0,0),(-1,0),(1,0),(0,-1),(0,1))
        def curr(x,y):return prior(x+true_offset[0],y+true_offset[1])
        def cost(dx,dy):
            return sum((curr(18+ox,18+oy)-
                        prior(18+ox+dx,18+oy+dy))**2
                       for ox,oy in taps)
        self.assertEqual(cost(*true_offset),0)
        self.assertGreater(min(cost(*v) for v in sparse),0)
        # The model says x=+2 (wrong), y=+4 (correct): adaptive samples
        # all x=-2..2 and y=3..5 and finds the actual perfect match.
        new = {(x,4+dy) for x in range(-2,3) for dy in (-1,0,1)}
        self.assertIn(true_offset,new)
        self.assertEqual(min(cost(*v) for v in sparse|new),0)

    def test_shader_cannot_change_previous_source_or_jitter(self):
        self.assertIn("vec2 nativeOffset = vec2(bestOffset)",SHADER)
        self.assertIn("PrevUV = Hruv + nativeOffset * params.renderSizeRcp",SHADER)
        self.assertIn("bestError < 0.002",SHADER)
        self.assertIn("invalidReprojection = true",SHADER)
        self.assertIn("verified_subpixel_jitter &&",CPP)
        self.assertIn("const vk::ImageView source_view = post_scene",CPP)
        self.assertIn("CaptureGsr2BeforeDepthlessPass",RASTER)

if __name__ == "__main__":
    unittest.main()
