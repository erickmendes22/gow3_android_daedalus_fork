#!/usr/bin/env python3
"""The A/B build must test exactly descriptor reuse and Vulkan recording."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
RUN=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
GAME=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
PACK=(ROOT/"ports/sotc/android/repack_verified_native.py").read_text()
class ControlledGpuAB(unittest.TestCase):
    def test_native_switches_separate_and_reversible(self):
        for env,key in (("SOTC_FAST_BIND","sotc_fast_bind"),("SOTC_RECORD_THREAD","sotc_record_thread")):
            self.assertIn("export "+env+"=${"+env+":-0}",RUN)
            self.assertIn('env.put("'+env+'",',GAME)
            self.assertIn('values["'+key+'"]?:"0"',UI)
            self.assertIn('save("'+key+'",if(it)"1" else "0")',UI)
            self.assertIn(key+"=0",PACK)
        self.assertIn("SotC GPU A/B: fast_bind=",RUN)
    def test_keep_other_graphics_invariants(self):
        for line in ("export SOTC_RB_ASYNC=0","export SOTC_UPLOAD_BUDGET_MB=0",
                     "export SOTC_ASYNC_SHADERS=0",
                     "export SOTC_LOD_LINGER=${SOTC_LOD_LINGER:-1}",
                     "export SOTC_TAA_OFF=${SOTC_TAA_OFF:-1}"):
            self.assertIn(line,RUN)
        self.assertIn("gpu-user-srt-phi6-gs-position",RUN)
if __name__=="__main__":unittest.main()
