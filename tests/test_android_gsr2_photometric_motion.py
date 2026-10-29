"""GSR2 regression for 2026-10-29 CUSA01623 raw temporal capture.

Reprojected motion on static scenery must not be trusted merely because the
camera matrix and temporal frame IDs are internally consistent.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHADER = (ROOT / "gpu/shadps4/video_core/host_shaders/gsr2_upscale.comp").read_text(encoding="utf-8")


def choose_static(current, previous_at_motion, previous_at_static, motion_pixels):
    # Mirrors the per-pixel YCoCg selection thresholds in the compute shader.
    motion_error = max(abs(a-b) for a, b in zip(previous_at_motion, current))
    static_error = max(abs(a-b) for a, b in zip(previous_at_static, current))
    return (motion_pixels > 0.25 and static_error < 0.16
            and static_error + 0.008 < motion_error * 0.75)


class PhotometricMotionRegression(unittest.TestCase):
    def test_static_scene_rejects_bad_model_matrix_motion(self):
        current = (0.22, 0.10, -0.05)
        self.assertTrue(choose_static(current, (0.42, 0.21, 0.11),
                                      (0.23, 0.095, -0.05), 1.8))

    def test_genuine_moving_scene_keeps_correct_reprojection(self):
        current = (0.22, 0.10, -0.05)
        self.assertFalse(choose_static(current, (0.23, 0.095, -0.05),
                                       (0.42, 0.21, 0.11), 1.8))

    def test_stationary_vector_does_not_trigger_replacement(self):
        current = (0.22, 0.10, -0.05)
        self.assertFalse(choose_static(current, (0.42, 0.21, 0.11),
                                       (0.23, 0.095, -0.05), 0.0))

    def test_shader_validates_before_temporal_weight_and_clipping(self):
        p_motion = SHADER.index("float candidateMotionPixels")
        p_weight = SHADER.index("float Wfactor =")
        p_clip = SHADER.index("vec3 clampedcolor =")
        self.assertLess(p_motion, p_weight)
        self.assertLess(p_weight, p_clip)
        self.assertIn("staticError + 0.008 < movingError * 0.75", SHADER)
        self.assertIn("HistoryColor = params.historyFilter != 0u", SHADER)
        self.assertIn("Motion = vec2(0.0);", SHADER)
        self.assertIn("if (invalidReprojection) alpha=1.0;", SHADER)

if __name__ == "__main__":
    unittest.main()
