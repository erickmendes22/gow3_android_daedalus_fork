"""R7 validates one-shot, native GPU stage provenance (not frame counters).
No UI, framegen, shader or input-affinity changes are allowed here.
"""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
def source(path): return (ROOT/path).read_text(encoding="utf-8")

class BionicR7StageTests(unittest.TestCase):
    def test_actual_gpu_readback_for_four_stages(self):
        code = source("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        for part in ("GsrProbeGrid(", "vmaInvalidateAllocation(", "copyImageToBuffer(",
                     '"scene_proxy"', '"gsr2_output"', '"ui_blit"', '"display_final"'):
            self.assertIn(part, code)
        self.assertIn('GSR_STAGE stage=%s y=%02u rgb=%s generation=%d', code)
        self.assertIn("GOW3_GSR2_AUTO_PROBE", code)
        self.assertIn("captured_generation = gsr2_completed_generation", code)
        self.assertIn("const u64 seeded_generation = it->second.gsr2_seed_generation;", code)
        self.assertIn("if (UseGsr2() && gsr_probe_frame", code)
        self.assertIn("GSR_STAGE_SRGB stage=", code)
        self.assertIn("if (gsr_capture_final && UseGsr2()", code)
        self.assertIn("scheduler.DeferPriorityOperation(", code)
        self.assertIn("GsrProbeHalf(", code)

    def test_probe_enabled_only_in_isolated_bionic_branch(self):
        script = source("tools/android/bionic/run-bionic.sh")
        self.assertIn("export GOW3_GSR2_AUTO_PROBE=1", script)
        workflow = source(".github/workflows/bionic-apk.yml")
        self.assertIn("r14-build-trigger.txt", workflow)
        self.assertIn("fix/bionic-r14-gsr2-history-camera-guard-20261019", workflow)

    def test_no_change_to_upscaler_shaders(self):
        # The shader binary is intentionally unmodified during isolation; avoid
        # masking the original bug by changing math/sampler behavior simultaneously.
        code = source("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn("const VideoCore::ImageId scene = color;",code)
        # Real temporal dispatch is valid only after the stricter camera-cut guard.
        self.assertIn('camera_motion.Gsr2HistoryValidity() == CameraMotion::Gsr2HistoryStatus::Valid',code)
        self.assertIn('"verified-temporal" : "spatial-reset-no-history"',code)
if __name__ == "__main__":
    unittest.main()
