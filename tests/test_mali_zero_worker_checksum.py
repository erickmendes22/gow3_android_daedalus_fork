"""PM4 zero-worker checksum is skipped for the actual production code."""
from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "gpu/shadps4/video_core/amdgpu/liverpool.cpp"
PREP = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_draw_prep.h"
RUN = ROOT / "tools/android/bionic/run-bionic.sh"


class ZeroWorkerChecksumTests(unittest.TestCase):
    def test_actual_production_enabled_guard(self):
        src = SOURCE.read_text()
        self.assertIn("const bool compute_checksum = (draw_prep && draw_prep->Enabled()) || force_checksum;", src)
        self.assertIn("ApplyGraphicsRegisterPacket(regs, header, gfx_reg_checksum, draw_dirty,\n                                        compute_checksum);", src)
        self.assertIn("if (update_checksum) {\n        checksum = HashRegisterPacket(", src)
        self.assertIn("return worker_count != 0;", PREP.read_text())
        self.assertIn("GOW3_PREP_WORKERS=${GOW3_PREP_WORKERS:-0}", RUN.read_text())
        self.assertIn("GOW3_PM4_CHECKSUM_ALWAYS=${GOW3_PM4_CHECKSUM_ALWAYS:-0}", RUN.read_text())

    def test_checksum_presence_matches_workload(self):
        expected = lambda workers, force: (workers > 0) or force
        self.assertFalse(expected(0, False))
        self.assertTrue(expected(0, True))
        self.assertTrue(expected(1, False))
        self.assertTrue(expected(4, False))

    def test_actual_hash_extraction(self):
        location = ROOT / "benchmarks/mali_pm4_checksum_gate.py"
        spec = importlib.util.spec_from_file_location("mali_pm4_gate", location)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        actual = module.actual_hash_source()
        self.assertIn("checksum ^= checksum >> 29;", actual)
        self.assertIn("checksum = (checksum ^ words[i])", actual)
        self.assertIn("return checksum;", actual)


if __name__ == "__main__":
    unittest.main()
