"""Regression checks for GSR2 sRGB stage analysis and generation alignment."""
import importlib.util
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYZER = ROOT / "tools/diagnostics/gsr2_stage_compare.py"
spec = importlib.util.spec_from_file_location("gsr2_stage_compare", ANALYZER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
GPU = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp"
LAUNCH = ROOT / "tools/android/bionic/run-bionic.sh"

def stage(name, gen, rgb):
    return "\n".join(
        f"GSR_STAGE_SRGB stage={name} y={y:02d} rgb={rgb * 32} generation={gen}"
        for y in range(18)
    )

class Gsr2StageIsolation(unittest.TestCase):
    def test_srgb_midgray_is_not_linear_midgray(self):
        # sRGB 0.5 is around 0.214 linear: the prior R19 comparison reported
        # an expected transfer-function difference as "GSR2 output dark".
        v = 0.5
        linear = ((v + 0.055) / 1.055) ** 2.4
        srgb = 1.055 * linear ** (1 / 2.4) - 0.055
        self.assertAlmostEqual(linear, 0.21404114048, places=8)
        self.assertAlmostEqual(srgb, v, places=8)

    def test_four_stages_are_compared_only_within_one_generation(self):
        log = "\n".join([
            stage("scene_proxy", 480, "000000"),
            stage("scene_proxy", 2400, "808080"),
            stage("gsr2_output", 2400, "808080"),
            stage("ui_blit", 2400, "808080"),
            stage("display_final", 2400, "808080"),
            stage("gsr2_output", 480, "FFFFFF"),
        ])
        frames = module.parse_log(log)
        full = module.report(frames, 2400)
        self.assertTrue(full["all_stages_matched_generation"])
        self.assertEqual(full["differences"]["scene_proxy_to_gsr2_output"]["mean_abs_rgb"], 0)
        partial = module.report(frames, 480)
        self.assertFalse(partial["all_stages_matched_generation"])
        self.assertEqual(partial["stages_missing"], ["ui_blit", "display_final"])
        self.assertEqual(partial["differences"]["scene_proxy_to_gsr2_output"]["mean_abs_rgb"], 255)

    def test_single_bad_quadrant_is_localized(self):
        zero = [[(0, 0, 0)] * 32 for _ in range(18)]
        bad = [[(255, 255, 255) if x < 16 and y < 9 else (0, 0, 0)
                for x in range(32)] for y in range(18)]
        result = module.compare(zero, bad)
        self.assertEqual(result["quadrant_mean_abs_rgb"], [255, 0, 0, 0])

    def test_instrumentation_records_real_vk_format_and_frame_generation(self):
        code = GPU.read_text(encoding="utf-8")
        for key in (
            "GsrProbeSrgbToLinear", "GsrProbeLinearToSrgb",
            "eB8G8R8A8Srgb", "eR8G8B8A8Srgb",
            "GSR_STAGE_SRGB stage=", "GSR_STAGE_LINEAR stage=",
            "captured_generation = gsr2_completed_generation",
            "it->second.gsr2_seed_generation",
            "GSR_STAGE_FINAL generation=",
            "GSR2_CAPTURE_CONTEXT generation=",
        ):
            with self.subTest(key=key):
                self.assertIn(key, code)
        self.assertNotIn("gsr_probe_present_frames == 2400", code)

    def test_original_android_gsr2_enabled_and_prefill_untouched(self):
        run = LAUNCH.read_text(encoding="utf-8")
        self.assertIn("export GOW3_GSR2_PREFILL_DISPLAY=1", run)
        self.assertIn("export GOW3_GSR2_AUTO_PROBE=1", run)
        self.assertIn("GOW3_UPSCALER=none", run)  # resolved by launch_env afterwards
        plan = (ROOT / "scripts/launch_env.py").read_text(encoding="utf-8")
        self.assertIn("updates['GOW3_UPSCALER'] = 'gsr2' if gsr2_requested else 'none'", plan)

if __name__ == "__main__":
    unittest.main()
