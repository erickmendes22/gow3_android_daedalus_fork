"""Numerical regression guards for source-log-constrained performance preflight."""
import importlib.util
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'benchmarks'
spec = importlib.util.spec_from_file_location('mali_draw_perf_gate', HERE / 'mali_draw_perf_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
FIXTURE = json.loads((HERE / 'fixtures/mali_g615_20261105_152530.json').read_text())


class TestGate(unittest.TestCase):
    def test_fixture_exact_reported_costs(self):
        self.assertEqual(FIXTURE['sampled_draws'], 462)
        self.assertEqual(FIXTURE['sampled_prepare_frames'], 8)
        self.assertAlmostEqual(FIXTURE['draws_per_frame_est'], 462)
        self.assertAlmostEqual(FIXTURE['non_pipeline_draw_cpu_ms_per_frame_est'], 14.82)
        self.assertAlmostEqual(FIXTURE['draw_cpu_ms_per_frame_est'], 22.38)

    def test_zero_and_regression_must_fail(self):
        for n in (0, -100, 300):
            passed, saving, threshold = gate.decide({'delta_ns_per_draw': n}, FIXTURE)
            self.assertFalse(passed)
            self.assertLess(saving, threshold)

    def test_modeled_ms_math_and_gate(self):
        passed, saving, threshold = gate.decide({'delta_ns_per_draw': 5000}, FIXTURE)
        self.assertFalse(passed)
        self.assertAlmostEqual(saving, 2.31)
        passed, saving, _ = gate.decide({'delta_ns_per_draw': 25000}, FIXTURE)
        self.assertTrue(passed)
        self.assertAlmostEqual(saving, 11.55)

    def test_reject_impossible_estimates_and_no_input_shortcuts(self):
        with self.assertRaises(ValueError):
            gate.estimate_ms_per_frame(123, 462, 1.2)
        with self.assertRaises(ValueError):
            gate.decide({'delta_ns_per_draw': 40000}, FIXTURE)
        with self.assertRaises(ValueError):
            gate.estimate_ms_per_frame(123, 0)

    def test_native_bench_outputs_timings(self):
        out = gate.run_bench(100000)
        self.assertEqual(out['kind'], 'synthetic_image_free_bind_only')
        self.assertGreater(out['baseline_ns_per_draw'], 0)
        self.assertGreater(out['candidate_ns_per_draw'], 0)


if __name__ == '__main__':
    unittest.main()
