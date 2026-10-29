"""CUSA01623 GSR2: reject model-camera motion using current/previous scene pixels."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHADER = (ROOT / "gpu/shadps4/video_core/host_shaders/gsr2_upscale.comp").read_text(encoding="utf-8")


def select_offset(patch_errors):
    """The shader prefers static if camera does not improve a five-tap patch."""
    stationary = patch_errors[(0, 0)]
    best = (0, 0)
    cost = stationary
    camera = patch_errors.get((2, 1), 1.e10)
    if camera + 0.00012 < stationary * .82:
        best, cost = (2, 1), camera
    if cost > 0.0006:
        for offset, error in patch_errors.items():
            if offset in ((0, 0), (2, 1)):
                continue
            regularized = error + .00003 * (offset[0] ** 2 + offset[1] ** 2) ** .5
            if regularized + .00004 < cost:
                best, cost = offset, regularized
    return best, cost


class Gsr2PhotometricHistory(unittest.TestCase):
    def test_still_scenery_beats_false_2px_camera_vector(self):
        patch = {(0, 0): .00004, (2, 1): .026,
                 (1, 0): .013, (-1, 0): .019}
        self.assertEqual(select_offset(patch)[0], (0, 0))

    def test_moving_character_searches_two_dimensional_offsets(self):
        patch = {(0, 0): .036, (2, 1): .028,
                 (-2, -2): .00008, (-2, 2): .026, (2, -2): .025}
        self.assertEqual(select_offset(patch)[0], (-2, -2))

    def test_proven_camera_motion_can_still_win(self):
        patch = {(0, 0): .029, (2, 1): .00005, (-2, -2): .009}
        self.assertEqual(select_offset(patch)[0], (2, 1))

    def test_unrelated_history_is_rejected(self):
        best, cost = select_offset({(0, 0): .055, (2, 1): .037,
                                   (1, 0): .043, (-1, 0): .040})
        self.assertGreaterEqual(cost, .012)

    def test_shader_has_real_pixel_matching_before_history_blend(self):
        self.assertIn("float Gow3HistoryPatchError(", SHADER)
        self.assertIn("const ivec2 taps[5]", SHADER)
        self.assertIn("const vec2 shifts[16]", SHADER)
        self.assertIn("staticError * 0.82", SHADER)
        self.assertIn("bestError < 0.012", SHADER)
        self.assertIn("Motion = (Hruv - PrevUV) * 2.0;", SHADER)
        self.assertIn("invalidReprojection = true;", SHADER)
        self.assertLess(SHADER.index("Gow3HistoryPatchError(Hruv, InputPos)"),
                        SHADER.index("float Wfactor ="))

if __name__ == "__main__":
    unittest.main()
