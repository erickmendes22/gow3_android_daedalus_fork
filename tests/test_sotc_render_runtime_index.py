#!/usr/bin/env python3
"""Guard the Android-only SRT dynamic-offset correctness fix."""
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "ports/sotc/android/stage_srt_arm64.py"

class SotcDynamicReadConstTest(unittest.TestCase):
    def test_shader_dynamic_window_is_not_cpu_stable(self):
        script = SOURCE.read_text()
        self.assertIn("case IR::Opcode::ReadConst:", script)
        self.assertIn("return (inst->Flags<u32>() & ReadConstDynamicWindowFlag) != 0;", script)
        self.assertIn("NeedsShaderDynamicOffset(src_off_dw) ||", script)
        self.assertIn("CopyFlatbufPlacement(readconst, original)", script)

if __name__ == "__main__":
    unittest.main()
