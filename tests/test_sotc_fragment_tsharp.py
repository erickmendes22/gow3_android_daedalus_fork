#!/usr/bin/env python3
"""Prevent SotC's incomplete material/lighting descriptor binding from regressing."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/"ports/sotc/android/stage_fragment_tsharp.py"
STAGE = ROOT/"ports/sotc/android/stage_renderer.py"
RUNNER = ROOT/"ports/sotc/android/run-sotc-bionic.sh"

class SotcFragmentTsharpTest(unittest.TestCase):
    def test_stage_isolated_from_gow3(self):
        self.assertIn("from stage_fragment_tsharp import patch_fragment_tsharp", STAGE.read_text())
        self.assertIn('shadps4/shader_recompiler/ir/passes/resource_patching_pass.cpp',
                      SCRIPT.read_text())

    def test_enable_fragment_without_vertex_gpu_hang(self):
        code = SCRIPT.read_text()
        self.assertIn("HwStage::Fragment", code)
        self.assertIn("HwStage::Compute || fragment_table", code)
        self.assertNotIn("HwStage::Vertex ||", code)
        self.assertIn("0x9d6f9bf4", code)
        self.assertIn("MatchSharpTable(resource.sharps[0])", code)
        self.assertIn("NumArrayDescriptors(info) + array_size + 1", code)
        self.assertIn("ir.ImageArrayHandle", code)

    def test_cache_does_not_reuse_old_unbound_descriptors(self):
        run = RUNNER.read_text()
        self.assertIn("export SOTC_ANDROID_FRAGMENT_TSHARP=1", run)
        self.assertIn("gpu-user-srt-phi4-barycentric-gs", run)
        self.assertIn("profile=$sotc_gpu_profile", run)
        self.assertNotIn("gpu-user-srt-phi2-", run)
        self.assertIn("export BB_READBACKS=2", run)
        self.assertIn("export SOTC_RB_ASYNC=0", run)

if __name__ == "__main__":
    unittest.main()
