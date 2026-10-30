"""Regression for measured (3,0)/(3,1) motion missing from native GSR2 search.

ZIP (9) has six frame-matched originals (640x360), with best scene
correlation around +3 X and +1 Y in frames 2-5. Previous shader tested
(4,0) and (2,2), but omitted those true candidates. This asserts shader
source and a small synthetic native scene; it is NOT on-device validation.
"""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
SHADER=(ROOT/"gpu/shadps4/video_core/host_shaders/gsr2_upscale.comp").read_text(encoding="utf-8")

class NativeCameraSearch(unittest.TestCase):
    def test_real_image_motion_not_skipped(self):
        self.assertIn("if (bestError > 0.00012)",SHADER)
        self.assertNotIn("if (bestError > 0.0006)",SHADER)
        self.assertIn("const ivec2 shifts[30] = ivec2[30]",SHADER)
        self.assertIn("for (int i = 0; i < 30; ++i)",SHADER)
        offsets=set((int(x),int(y)) for x,y in re.findall(r"ivec2\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)",SHADER.split("const ivec2 shifts[30]",1)[1].split("for (int i",1)[0]))
        for dx,dy in ((3,0),(-3,0),(3,1),(-3,-1),(3,-1),(-3,1),(2,1),(-2,-1),(1,2),(-1,-2)):
            with self.subTest(offset=(dx,dy)):
                self.assertIn((dx,dy),offsets)
        self.assertEqual(len(offsets),30)

    def test_ground_truth_three_by_one_is_not_represented_by_old_sparse_set(self):
        old={(0,0),(-4,0),(4,0),(0,-4),(0,4),(-2,-2),(-2,2),(2,-2),(2,2),
             (-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)}
        self.assertNotIn((3,1),old)
        self.assertNotIn((3,0),old)
        # Same 5-tap correspondence objective, with a synthetic perfectly
        # shifted image: the known true motion has zero mismatch.
        img=[[((x*73)^(y*39)^(x*y*17))&255 for x in range(24)] for y in range(24)]
        def err(dx,dy):
            return sum((img[y][x]-img[y+1+dy][x+3+dx])**2
                       for x,y in ((7,7),(6,7),(8,7),(7,6),(7,8)))/5
        # Current pixel at (x+3,y+1) corresponds to previous at (x,y).
        # For this convention the matching candidate is (-3,-1).
        self.assertEqual(err(-3,-1),0)
        self.assertGreater(min(err(dx,dy) for dx,dy in old),0)

    def test_native_photometric_guard_and_zero_jitter_remain(self):
        self.assertIn("Gow3NativePatchError(InputPos, shifts[i])",SHADER)
        self.assertIn("PreviousNativeYCoCg",SHADER)
        self.assertIn("if (bestError < 0.002)",SHADER)
        self.assertIn("invalidReprojection = true;",SHADER)
        u=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp").read_text()
        self.assertIn("verified_subpixel_jitter &&",u)
        self.assertIn("GSR2_RASTER_JITTER_GUARD",u)

if __name__ == "__main__":
    unittest.main()
