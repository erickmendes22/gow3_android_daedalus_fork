"""Pure numeric regressions for the same-flip PS4 VideoOut color transform.

The device logs 212023 / 215958 showed widespread color grading over the
same geometry (especially flip 7200/9600); a raw 5/16 color-difference rule
switched the whole screen between guest and temporal history.
"""
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHADER = ROOT / "gpu/shadps4/video_core/host_shaders/gsr2_prehud_composite.comp"


def clamp(x, lo, hi):
    return min(max(x, lo), hi)


def smoothstep(a, b, x):
    t = clamp((x-a)/(b-a), 0.0, 1.0)
    return t*t*(3.0-2.0*t)


def fit_grade(pairs):
    assert len(pairs) == 16
    gain, bias = [], []
    for k in range(3):
        accepted = [p for p in pairs if max(abs(p[0][i]-p[1][i]) for i in range(3)) <= 0.55]
        ax = sum(p[0][k] for p in accepted)/max(len(accepted), 1)
        ay = sum(p[1][k] for p in accepted)/max(len(accepted), 1)
        var = sum((p[0][k]-ax)**2 for p in accepted)/max(len(accepted), 1)
        cov = sum((p[0][k]-ax)*(p[1][k]-ay) for p in accepted)/max(len(accepted), 1)
        g = clamp(cov / max(var, 0.00002), 0.55, 2.25) if var > 0.00002 else 1.0
        gain.append(g)
        bias.append(clamp(ay-g*ax, -0.28, 0.28))
    bad = sum(
        max(abs(clamp(a[k]*gain[k]+bias[k], 0, 1)-b[k]) for k in range(3)) > 0.12
        for a, b in pairs
    )
    return gain, bias, (1.0 if len(accepted) < 8 else smoothstep(3.0, 11.0, float(bad))), bad


class Gsr2GradeTests(unittest.TestCase):
    def test_shader_global_rule_matches_model(self):
        shader = SHADER.read_text()
        self.assertIn("shared vec3 gradeGain;", shader)
        self.assertIn("shared vec3 gradeBias;", shader)
        self.assertIn("sumXY*(1.0/16.0)-meanX*meanY", shader)
        self.assertIn("smoothstep(3.0,11.0,bad);", shader)
        self.assertNotIn("incompatibleScene=uint(different>=5u)", shader)
        self.assertIn("vec3 result=mix(restored,guest,guestWeight);", shader)

    def test_widespread_brightness_grade_is_not_incompatible(self):
        # 16 different pixels of one and the same scene with a global grade.
        before = [(0.08+0.035*i, 0.03+0.022*i, 0.04+0.027*i)
                  for i in range(16)]
        after = [tuple(1.22*c+0.07 for c in pix) for pix in before]
        grade, bias, fallback, bad = fit_grade(list(zip(before, after)))
        self.assertEqual(bad, 0)
        self.assertEqual(fallback, 0)
        for k in range(3):
            self.assertAlmostEqual(grade[k], 1.22, places=5)
            self.assertAlmostEqual(bias[k], 0.07, places=5)

    def test_an_unrelated_scene_falls_back_smoothly(self):
        before = [(0.05+0.05*i, 0.06+0.03*i, 0.07+0.025*i)
                  for i in range(16)]
        after = [(0.8 if i % 2 else 0.05,
                  0.2 if i % 3 else 0.8,
                  0.8 if i % 4 else 0.03) for i in range(16)]
        _gain, _bias, fallback, bad = fit_grade(list(zip(before, after)))
        self.assertGreaterEqual(bad, 11)
        self.assertEqual(fallback, 1.0)

    def test_small_hud_change_keeps_scene_temporal(self):
        before = [(0.03+0.03*i, 0.1+0.018*i, 0.05+0.022*i)
                  for i in range(16)]
        after = [tuple(1.04*c + 0.02 for c in pix) for pix in before]
        after[3] = (1.0, 1.0, 1.0)
        after[7] = (1.0, 1.0, 1.0)
        _g, _b, fallback, bad = fit_grade(list(zip(before, after)))
        self.assertEqual(fallback, 0.0)
        self.assertEqual(bad, 2)


if __name__ == "__main__":
    unittest.main()
