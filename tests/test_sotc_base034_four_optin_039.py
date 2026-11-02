#!/usr/bin/env python3
"""SotC 0.1.39: original 0.1.34 runtime, four OFF-by-default optional 0.1.35 tests."""
import unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
JAVA=(R/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI=(R/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
SHELL=(R/"ports/sotc/android/run-sotc-bionic.sh").read_text()
REPACK=(R/"ports/sotc/android/repack_base034_optin_039.py").read_text()
INI=(R/"ports/sotc/android/package_sotc_runtime.py").read_text()
class Baseline034(unittest.TestCase):
    def test_fixed_original_defaults_are_preserved(self):
        for flag,value in [["SOTC_ASYNC_SHADERS","0"],["SOTC_ASYNC_COMPUTE","0"],["SOTC_PRESENT_FULL_BLIT","1"],["SOTC_STAGE_SPEC_MEMO","1"],["SOTC_STAGE_SNAPSHOT_SWAP","1"],["SOTC_REG_SNAPSHOT_MEMO","1"],["SOTC_RT_MEMO","1"],["SOTC_VM_RANGE_CACHE","1"],["SOTC_PERF_PROFILE","0"],["SOTC_PIPELINE_BIND_MEMO","1"],["SOTC_VERTEX_INPUT_MEMO","1"],["SOTC_DESCRIPTOR_SLOT_REUSE","1"],["SOTC_FAST_BIND","0"],["SOTC_RECORD_THREAD","0"],["SOTC_RB_ASYNC","0"],["SOTC_RB_STREAM","1"],["SOTC_RB_STREAM_MAX_KB","512"]]:
            self.assertIn('env.put("'+flag+'","'+value+'");',JAVA,flag)
        for old in ("sotc_rb_narrow","sotc_flush_us","sotc_rb_ahead","sotc_shadow_stagger","sotc_perf_mode"):
            self.assertNotIn('setting("'+old+'")',JAVA)
        for forbidden in ("SOTC_RB_AHEAD","SOTC_RB_NARROW","SOTC_FLUSH_US","SOTC_FLUSH_EVERY","SOTC_SHADOW_STAGGER"):
            self.assertNotIn('env.put("'+forbidden+'"',JAVA)
        self.assertIn("sotc_readbacks=2",INI)
        self.assertIn("sotc_rb_stream=1",INI)
        self.assertIn("SOTC_TAA_OFF",JAVA)
    def test_four_independent_disabled_optional_settings(self):
        extras=[["sotc_trial039_readback_1m","SOTC_RB_STREAM_MAX_KB","1024"],["sotc_trial039_dma_32m","SOTC_DMA_MERGE_MAX","32"],["sotc_trial039_cpu_31p","SOTC_WRITE_AHEAD_PAGES","31"],["sotc_trial039_arena_8p","SOTC_ARENA_GROUP","8"]]
        self.assertEqual(len(extras),4)
        for key,flag,value in extras:
            self.assertIn('(values["'+key+'"]?:"0")=="1"',UI)
            self.assertIn('save("'+key+'",if(it)"1" else "0")',UI)
            self.assertIn('if ("1".equals(setting("'+key+'"))) env.put("'+flag+'","'+value+'");',JAVA)
        self.assertNotIn("advancedOptionsVisible",UI)
        self.assertNotIn('values["sotc_perf_mode"]',UI)
    def test_repack_verifies_exact_original_binary(self):
        self.assertIn('OLD_VERSION="0.1.34-boot-test"',REPACK)
        self.assertIn('NEW_VERSION="0.1.39-boot-test"',REPACK)
        self.assertIn("original_shell=shell.replace(NEW_CHECK,OLD_CHECK)",REPACK)
        self.assertIn('case "$SOTC_RB_STREAM_MAX_KB" in 512|1024)',SHELL)
        self.assertIn("SOTC_RB_STREAM_MAX_KB:-512",SHELL)
        self.assertNotIn("SOTC_FLUSH_EVERY",SHELL)
        self.assertNotIn("SOTC_RB_AHEAD=",SHELL)
if __name__=="__main__": unittest.main()
