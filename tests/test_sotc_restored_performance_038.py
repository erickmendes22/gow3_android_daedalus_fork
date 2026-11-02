#!/usr/bin/env python3
"""0.1.38: previously active native fastpaths must remain in the default profile."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
JAVA=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
SH=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
REPACK=(ROOT/"ports/sotc/android/repack_restored_038.py").read_text()
class Restored(unittest.TestCase):
    def test_full_native_fastpaths_default_on(self):
        self.assertIn('values["sotc_perf_mode"]?:"performance"',UI)
        self.assertIn('if (!"compat".equals(perfMode))',JAVA)
        for flag in ["SOTC_RB_EARLY","SOTC_HEAP_FAST","SOTC_DMA_MERGE","SOTC_DMA_INCR","SOTC_COPY_BATCH","SOTC_EVICT_ASYNC","SOTC_DEPTH_TWIN","SOTC_TC_SKIP_EMPTY","SOTC_SAMPLER_MEMO","SOTC_FIND_MEMO","SOTC_MEMO_ADDR_GEN","SOTC_PIPE_MEMO","SOTC_RT_FAST","SOTC_POP_FAST","SOTC_INDIRECT_DIRECT","SOTC_CP_YIELD","SOTC_DRIVER_CACHE"]:
            self.assertIn('env.put("'+flag+'","1");',JAVA,flag)
        for flag,value in [["SOTC_RB_NARROW","0"],["SOTC_RB_STREAM_MAX_KB","512"],["SOTC_WRITE_AHEAD_PAGES","15"],["SOTC_DMA_MERGE_MAX","16"],["SOTC_ARENA_GROUP","4"]]:
            self.assertIn('env.put("'+flag+'","'+value+'");',JAVA,flag)
    def test_previous_fps_regressions_not_reintroduced(self):
        self.assertNotIn('env.put("SOTC_FLUSH_EVERY"',JAVA)
        self.assertNotIn('env.put("SOTC_FLUSH_US","0")',JAVA)
        self.assertNotIn('env.put("SOTC_RB_NARROW","64")',JAVA)
        self.assertNotIn("SOTC_FLUSH_EVERY",SH)
        self.assertIn('env.put("SOTC_VM_RANGE_CACHE","1");',JAVA)
        self.assertIn('env.put("SOTC_RB_STREAM","1");',JAVA)
        self.assertIn('env.put("BB_READBACKS",rbMode)',JAVA)
        self.assertIn('env.put("SOTC_FAST_BIND","0");',JAVA)
        self.assertIn('env.put("SOTC_ASYNC_SHADERS","0");',JAVA)
    def test_simple_ui_and_native_consistency(self):
        self.assertIn('"compat" to',UI)
        self.assertIn("SOTC_TAA_OFF",JAVA)
        self.assertNotIn("LABORATÓRIO DE DESEMPENHO",UI)
        self.assertIn('OLD_VERSION="0.1.37-boot-test"',REPACK)
        self.assertIn('NEW_VERSION="0.1.38-boot-test"',REPACK)
        self.assertIn('if changed!=["runtime-manifest.json"]',REPACK)
if __name__=="__main__":
    unittest.main()
