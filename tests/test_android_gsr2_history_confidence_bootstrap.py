"""CUSA01623 GSR2 history bootstrap regression.

Unlike a source-text presence check, this models the exact confidence
recurrence discovered in the shader and the RGBA-zero clears in vk_gsr2.
Previous code wrote old Wfactor as new history alpha:
    a[0]=0, a[n+1]=clamp(abs(a[n]),0,1)
=> a[n] == 0 forever, even across valid temporal frames.

After the fix each finite current-frame reconstruction initializes its own
next-frame confidence to one. An invalid output writes zero, and the next
finite spatial result repairs confidence. Does NOT measure on-device image.
"""
from pathlib import Path
import math
import unittest

ROOT=Path(__file__).resolve().parents[1]
S=(ROOT/"gpu/shadps4/video_core/host_shaders/gsr2_upscale.comp").read_text()
H=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_gsr2.cpp").read_text()

def old_confidence(previous, num_frames):
    out=[]
    for _ in range(num_frames):
        w=max(0.,min(abs(previous),1.))
        previous=w
        out.append(previous)
    return out

def fixed_confidence(previous, current_colors):
    out=[]
    for color in current_colors:
        color_finite=all(math.isfinite(channel) for channel in color)
        previous=1. if color_finite else 0.
        out.append(previous)
    return out

class TemporalConfidenceBootstrap(unittest.TestCase):
    def test_reproduce_absorbing_zero_on_cleared_history(self):
        self.assertIn("cmd.clearColorImage(vk::Image(history_image[i])",H)
        self.assertIn("std::array<float, 4>{}",H)
        self.assertEqual(old_confidence(0.0,10),[0.0]*10)
        self.assertEqual(old_confidence(1.0,4),[1.0]*4)

    def test_valid_reset_frame_bootstraps_next_temporal_frame(self):
        colors=[(0.1,0.2,0.3)]*6
        self.assertEqual(fixed_confidence(0.0,colors),[1.0]*6)
        self.assertNotIn("vec4(Upsampledcw.xyz, Wfactor)",S)
        self.assertIn("float nextHistoryConfidence = validCurrentColor ? 1.0 : 0.0;",S)
        self.assertIn("vec4(Upsampledcw.xyz, nextHistoryConfidence)",S)

    def test_invalid_current_output_does_not_poison_new_history(self):
        colors=[(0.3,0.4,0.5), (float("nan"),0.1,0.2),
                (0.2,0.2,0.2),(float("inf"),0.0,0.0),(0.7,0.6,0.2)]
        self.assertEqual(fixed_confidence(0.0,colors),[1.0,0.0,1.0,0.0,1.0])
        self.assertIn("!any(isnan(Upsampledcw.xyz))",S)
        self.assertIn("!any(isinf(Upsampledcw.xyz))",S)
        self.assertIn("if (!validCurrentColor) Upsampledcw.xyz = vec3(0.0);",S)

    def test_existing_temporal_history_rejection_and_scene_selection_preserved(self):
        self.assertIn("float Wfactor = invalidReprojection ? 0.0",S)
        self.assertIn("if (invalidReprojection) alpha=1.0;",S)
        self.assertIn("float rejectHistory=smoothstep(0.055,0.145,discrepancy)",S)
        self.assertIn("Gow3NativePatchError(InputPos, bestOffset)",S)
        self.assertIn("float alphasum = max(EPSILON, basealpha + Upsampledcw.w);",S)
        self.assertIn("cmd.clearColorImage(vk::Image(history_image[i])",H)

if __name__=="__main__":
    unittest.main()
