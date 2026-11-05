"""Mali G615 frame-budget math must rule out overpromised CPU-only gains."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/mali_frame_budget_gate.py"
spec = importlib.util.spec_from_file_location("mali_frame_budget_gate", SOURCE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
FIXTURE = json.loads((ROOT / "benchmarks/fixtures/mali_g615_20261105_152530.json").read_text())


class MaliFrameBudgetGate(unittest.TestCase):
    def test_savings_are_limited_by_stage(self):
        self.assertAlmostEqual(
            gate.budget(7.4, 0)["max_fps"], 7.4, places=7)
        a = gate.budget(7.4, FIXTURE["pipeline_lookup_ms_per_frame_est"])
        self.assertLess(a["max_gain_percent"], 10)
        b = gate.budget(7.4, FIXTURE["non_pipeline_draw_cpu_ms_per_frame_est"])
        self.assertLess(b["max_gain_percent"], 15)
        c = gate.budget(7.4, FIXTURE["draw_cpu_ms_per_frame_est"])
        self.assertLess(c["max_gain_percent"], 25)

    def test_required_reduction_is_not_double_counted(self):
        baseline = 1000 / 7.4
        for target in (10, 20, 25):
            saving = gate.required_ms(7.4, target)
            self.assertAlmostEqual(
                1000 / (baseline - saving), 7.4 * (1 + target / 100))

    def test_invalid_inputs_rejected(self):
        for fps, elapsed in ((0, 1), (7.4, -1), (7.4, 1000 / 7.4)):
            with self.assertRaises(ValueError):
                gate.budget(fps, elapsed)
        with self.assertRaises(ValueError):
            gate.required_ms(7.4, 0)

    def test_fixture_consistency(self):
        self.assertAlmostEqual(
            FIXTURE["pipeline_lookup_ms_per_frame_est"] +
            FIXTURE["non_pipeline_draw_cpu_ms_per_frame_est"],
            FIXTURE["draw_cpu_ms_per_frame_est"])
        self.assertEqual(FIXTURE["device"], "Mali-G615 MC6")


if __name__ == "__main__":
    unittest.main()
