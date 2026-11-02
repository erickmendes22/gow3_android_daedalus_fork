#!/usr/bin/env python3
"""Regression: installed 0.1.35 lab preferences must not affect 0.1.37 stable."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
JAVA = (ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI = (ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
SH = (ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
REPACK = (ROOT/"ports/sotc/android/repack_stable_037.py").read_text()

class CleanStable(unittest.TestCase):
    def test_original_034_effective_defaults_override_persisted_lab_settings(self):
        defaults={
        "SOTC_ASYNC_SHADERS": "0",
        "SOTC_ASYNC_COMPUTE": "0",
        "SOTC_PRESENT_FULL_BLIT": "1",
        "SOTC_STAGE_SPEC_MEMO": "1",
        "SOTC_STAGE_SNAPSHOT_SWAP": "1",
        "SOTC_REG_SNAPSHOT_MEMO": "1",
        "SOTC_RT_MEMO": "1",
        "SOTC_VM_RANGE_CACHE": "1",
        "SOTC_PERF_PROFILE": "0",
        "SOTC_PIPELINE_BIND_MEMO": "1",
        "SOTC_VERTEX_INPUT_MEMO": "1",
        "SOTC_DESCRIPTOR_SLOT_REUSE": "1",
        "SOTC_FAST_BIND": "0",
        "SOTC_RECORD_THREAD": "0",
        "SOTC_RB_ASYNC": "0",
        "SOTC_RB_STREAM": "1",
        "SOTC_RB_STREAM_MAX_KB": "512"
}
        for key, value in defaults.items():
            self.assertIn('env.put("'+key+'","'+value+'");', JAVA)
        for key in ("sotc_fast_bind","sotc_stage_spec_memo","sotc_perf_profile",
                    "sotc_rb_async","sotc_rb_stream","sotc_vm_range_cache"):
            self.assertNotIn('setting("'+key+'")', JAVA)
        for legacy in ("SOTC_RB_NARROW","SOTC_DMA_MERGE","SOTC_COPY_BATCH",
                       "SOTC_SHADOW_STAGGER","SOTC_FLUSH_EVERY"):
            self.assertNotIn('env.put("'+legacy+'"', JAVA)
    def test_two_isolated_experiments_no_forced_flag_in_stable(self):
        self.assertIn('if ("ahead".equals(perfMode))', JAVA)
        self.assertIn('env.put("SOTC_RB_AHEAD","1");', JAVA)
        self.assertIn('} else if ("submit".equals(perfMode))', JAVA)
        self.assertIn('env.put("SOTC_FLUSH_US","1000");', JAVA)
        self.assertNotIn("SOTC_FLUSH_EVERY",SH)
        self.assertNotIn("SOTC_RB_AHEAD=",SH)
        self.assertIn("SOTC_TAA_OFF",JAVA)
        self.assertIn("BB_READBACKS",JAVA)
    def test_small_menu_and_packaged_native_baseline(self):
        self.assertNotIn("advancedOptionsVisible",UI)
        self.assertNotIn("LABORATÓRIO DE DESEMPENHO",UI)
        self.assertNotIn("sotc_rb_narrow",UI)
        self.assertIn('values["sotc_perf_mode"]?:"stable"',UI)
        self.assertIn("0.1.37 clean stable",UI)
        self.assertIn('OLD_VERSION="0.1.36-boot-test"',REPACK)
        self.assertIn('NEW_VERSION="0.1.37-boot-test"',REPACK)
        self.assertIn('if changed!=["runtime-manifest.json"]',REPACK)
if __name__ == "__main__":
    unittest.main()
