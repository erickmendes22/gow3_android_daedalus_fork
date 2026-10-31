#!/usr/bin/env python3
"""Guard real SotC ZPASS and conditional GPU rendering against placeholder implementations."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "ports/sotc/android/stage_renderer.py"
BACKEND = ROOT / "ports/sotc/android/stage_pm4_predication.py"
COMMANDS = ROOT / "ports/sotc/android/stage_pm4_predication_commands.py"
RUN = ROOT / "ports/sotc/android/run-sotc-bionic.sh"
VENDOR = ROOT / "ports/sotc/android/predication_upstream"

class RealPredicationPort(unittest.TestCase):
    def test_original_full_algorithm_is_vendored(self):
        cpp = (VENDOR / "vk_predication.cpp").read_text()
        header = (VENDOR / "vk_predication.h").read_text()
        comp = (VENDOR / "occlusion_predicate.comp").read_text()
        for s in ("vk::QueryType::eOcclusion", "copyQueryPoolResults",
                  "beginConditionalRenderingEXT", "endConditionalRenderingEXT",
                  "EnableFromZpass", "EnableFromBool", "ResetZpassCounting",
                  "DumpZpassCounters", "ReadGuestZpass", "ResolveRecord"):
            self.assertIn(s, cpp)
        self.assertIn("bool IsGpuPredicationActive()", header)
        self.assertIn("predicates[dst_index]", comp)

    def test_stages_gpu_and_pm4_commands_in_order(self):
        s = STAGE.read_text()
        a = s.index("patch_predication_backend(out)")
        b = s.index("patch_predication_commands(out)")
        self.assertLess(a,b)
        code = COMMANDS.read_text()
        for word in ("PM4CmdSetPredication", "PM4CmdPredExec", "PredicationOp::Zpass",
                     "PredicationOp::Bool32", "PredicationOp::Bool64",
                     "ShouldSkipPredicatedPacket", "GetPredication()",
                     "IsPacketPredicated()", "DumpZpassCounters",
                     "BeginDraw(cmdbuf", "EndDraw(cmdbuf",
                     "PrepareDrawQuery", "RestorePredicatedIndexBase"):
            self.assertIn(word,code)
        self.assertNotIn('Unimplemented IT_SET_PREDICATION',code)

    def test_no_false_ghosting_reversion(self):
        s = RUN.read_text()
        for k in ("SOTC_CP_THREADS=0","SOTC_RECORD_THREAD=0",
                  "SOTC_INDIRECT_DIRECT=0","BB_READBACKS=2","SOTC_RB_ASYNC=0",
                  "SOTC_ANDROID_FRAGMENT_TSHARP=1"):
            self.assertIn("export "+k,s)
        self.assertIn("gpu-user-srt-phi4-barycentric-gs",s)
        self.assertNotIn("export SOTC_ADRENO_WAVE32=0",s)
        self.assertIn("SOTC_TAA_OFF",s)

    def test_conditional_extension_is_not_faked(self):
        s = BACKEND.read_text()
        self.assertIn("conditional_rendering = add_extension",s)
        self.assertIn("conditional_rendering = conditional_rendering &&",s)
        self.assertIn("device_chain.unlink<vk::PhysicalDeviceConditionalRenderingFeaturesEXT>()",s)
        self.assertIn("SotC PM4 predication: conditional_rendering=",s)
        self.assertIn("vk::BufferUsageFlagBits::eConditionalRenderingEXT",s)

if __name__ == "__main__":
    unittest.main()
