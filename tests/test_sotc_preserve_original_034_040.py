#!/usr/bin/env python3
"""SotC 0.1.40: 0.1.34 Java/Compose MUST be byte-identical after removing only four added options."""
import hashlib
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
JAVA=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
SHELL=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
INI=(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text()
REPACK=(ROOT/"ports/sotc/android/repack_original_menu_040.py").read_text()
UPSTREAM=ROOT/"upstream-sotc/gpu/shadps4/video_core/buffer_cache/buffer_cache.cpp"
OPTIONS=[
    ("sotc_trial039_readback_1m","SOTC_RB_STREAM_MAX_KB","1024"),
    ("sotc_trial039_dma_32m","SOTC_DMA_MERGE_MAX","32"),
    ("sotc_trial039_cpu_31p","SOTC_WRITE_AHEAD_PAGES","31"),
    ("sotc_trial039_arena_8p","SOTC_ARENA_GROUP","8"),
]
def github_blob_sha(text):
    raw=text.encode("utf-8")
    return hashlib.sha1(("blob "+str(len(raw))+"\\0").encode()+raw).hexdigest()

class RestoreOriginalMenu(unittest.TestCase):
    def test_original_034_java_byte_for_byte_preserved(self):
        start=JAVA.index("                // 0.1.40: the ORIGINAL 0.1.34 options")
        end=JAVA.index('            }\\n            env.put("GOW3_DISPLAY_HZ"',start)
        reconstructed=JAVA[:start]+JAVA[end:]
        self.assertEqual(github_blob_sha(reconstructed),"4b1662e5f83eb3547c6aa1201420edf2a45254a4",
                         "The 0.1.34 launcher logic must be byte-for-byte original")
    def test_original_034_ui_byte_for_byte_preserved(self):
        start=UI.index('                    Text(if(pt) "0.1.35 — QUATRO TESTES ADICIONAIS (DESATIVADOS)"')
        end=UI.index('                    SotcToggle(if(pt) "Histórico temporal TAA (ghosts)"',start)
        reconstructed=(UI[:start]+UI[end:]).replace("DAEDALUS • 0.1.40 — base 0.1.34",
                                                    "DAEDALUS • 0.1.34 readback stream")
        self.assertEqual(github_blob_sha(reconstructed),"38bb95d032aa6def9187f55d4d38da82e6377cff",
                         "Original 0.1.34 menu, all original toggles and controls must remain unchanged")
    def test_four_independent_options_all_off_default(self):
        self.assertEqual(len(OPTIONS),4)
        for key,env,value in OPTIONS:
            with self.subTest(option=key):
                self.assertIn('(values["'+key+'"]?:"0")=="1"',UI)
                self.assertIn('save("'+key+'",if(it)"1" else "0")',UI)
                self.assertIn('if ("1".equals(setting("'+key+'"))) env.put("'+env+'","'+value+'");',JAVA)
        self.assertNotIn("sotc_perf_mode",UI)
        self.assertNotIn('setting("sotc_perf_mode")',JAVA)
        for dangerous in ("SOTC_RB_AHEAD","SOTC_RB_NARROW","SOTC_FLUSH_EVERY","SOTC_FLUSH_US"):
            self.assertNotIn('env.put("'+dangerous+'"',JAVA)
    def test_original_034_readback_default_and_package(self):
        self.assertIn('env.put("BB_READBACKS",rbMode)',JAVA)
        self.assertIn('env.put("SOTC_RB_STREAM",',JAVA)
        self.assertIn('env.put("SOTC_RB_STREAM_MAX_KB","512");',JAVA)
        self.assertIn("sotc_rb_stream=1",INI)
        self.assertIn("sotc_readbacks=2",INI)
        self.assertIn("SOTC_RB_STREAM_MAX_KB:-512",SHELL)
        self.assertIn('case "$SOTC_RB_STREAM_MAX_KB" in 512|1024)',SHELL)
        self.assertIn('OLD_VERSION="0.1.34-boot-test"',REPACK)
        self.assertIn('NEW_VERSION="0.1.40-boot-test"',REPACK)
    @unittest.skipUnless(UPSTREAM.exists(),"Pinned native code check requires upstream checkout")
    def test_four_extras_are_native_implemented(self):
        native=UPSTREAM.read_text()
        for _,env,_ in OPTIONS:
            self.assertIn('std::getenv("'+env+'")',native,
                          "Not a real native flag in original 0.1.34 renderer: "+env)

if __name__=="__main__":
    unittest.main()
