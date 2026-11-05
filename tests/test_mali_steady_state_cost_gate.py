"""Ground sample factors in four actual G615 no-pipeline-build intervals."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
module_path=ROOT/"benchmarks/mali_steady_state_cost_gate.py"
spec=importlib.util.spec_from_file_location("mali_steady",module_path)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class BudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=gate.load()
        cls.d=gate.calculate(cls.fixture)

    def test_exact_source_and_steady_fps(self):
        self.assertEqual(self.fixture["source_sha256"],
                         "9ca4977665a27011cc9bcb5977d4cb309649909c9a816cb96ce443b62e9cf97f")
        self.assertEqual(self.d["approx_frames"],256)
        self.assertEqual(self.d["interval_wall_ms"],35724)
        self.assertAlmostEqual(self.d["approx_fps"],7.16605083417)

    def test_correct_factors_for_all_stages(self):
        self.assertEqual(self.fixture["sample_factors"]["gpu_draw_cpu"],256)
        self.assertEqual(self.fixture["sample_factors"]["pm4_submit_wall"],32)
        self.assertEqual(self.fixture["sample_factors"]["submit_host_copy_wait"],32)
        self.assertEqual(self.fixture["sample_factors"]["submit_throttle"],1)

    def test_measured_per_frame_upper_bounds(self):
        expected={"gpu_draw_cpu":22.38,"pipeline_lookup":7.56,
                  "pm4_submit_wall":56.21875,
                  "submit_host_copy_wait":0.0975,
                  "submit_throttle":0.0412109375,
                  "fence_wait":2.05,
                  "ahb_total":6.33125}
        for name,value in expected.items():
            with self.subTest(stage=name):
                self.assertAlmostEqual(self.d["stages"][name]["estimated_ms_per_frame"],value)

    def test_reject_small_hypotheses_before_apk(self):
        for name in ("submit_host_copy_wait","submit_throttle",
                     "pipeline_lookup","fence_wait","ahb_total"):
            self.assertLess(self.d["stages"][name]["estimated_ms_per_frame"],10)

    def test_pm4_is_nested_not_an_additive_stage(self):
        self.assertGreater(self.d["stages"]["pm4_submit_wall"]["estimated_ms_per_frame"],
                           self.d["stages"]["gpu_draw_cpu"]["estimated_ms_per_frame"])
        self.assertTrue(any("PM4 wall" in x and "suspensions" in x
                            for x in self.fixture["notes"]))

    def test_optimistic_fps_bound_not_claimed_real(self):
        draw=self.d["stages"]["gpu_draw_cpu"]["estimated_ms_per_frame"]
        max_fps=gate.optimistic_effect(self.d,draw)
        self.assertAlmostEqual(max_fps,8.541,delta=.05)
        self.assertGreater(max_fps,self.d["approx_fps"])

if __name__=="__main__":unittest.main()
