#!/usr/bin/env python3
"""GPU readback choice 0/1/2 reaches the SotC Bionic emulator and keeps 2 as default."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
JAVA=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
RUN=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
PACK=(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text()

class ReadbackModes(unittest.TestCase):
    def test_modes_0_1_2_and_invalid_fallback(self):
        self.assertIn('values["sotc_readbacks"]?:"2"',UI)
        self.assertIn('save("sotc_readbacks",it)',UI)
        for n in ("0","1","2"):
            self.assertIn('"'+n+'" to (if(pt)',UI)
            self.assertIn("  "+n+") echo",RUN)
        self.assertIn('String rbMode=setting("sotc_readbacks");',JAVA)
        self.assertIn('!"0".equals(rbMode)',JAVA)
        self.assertIn('!"1".equals(rbMode)',JAVA)
        self.assertIn('!"2".equals(rbMode)',JAVA)
        self.assertIn('rbMode="2";',JAVA)
        self.assertIn('env.put("BB_READBACKS",rbMode);',JAVA)
        self.assertIn("export BB_READBACKS="+chr(36)+"{BB_READBACKS:-2}",RUN)
        self.assertIn('case "$BB_READBACKS" in',RUN)
        self.assertIn("sotc_readbacks=2",PACK)
    def test_rt_memo_enabled_with_fallback(self):
        self.assertIn("export SOTC_RT_MEMO="+chr(36)+"{SOTC_RT_MEMO:-1}",RUN)
        self.assertIn("sotc_rt_memo=1",PACK)
        self.assertIn('env.put("SOTC_RT_MEMO",',JAVA)
        self.assertIn('save("sotc_rt_memo",if(it)"1" else "0")',UI)
        self.assertIn("patch_sotc_rt_memo(out)",(ROOT/"ports/sotc/android/stage_renderer.py").read_text())

if __name__=="__main__": unittest.main()
