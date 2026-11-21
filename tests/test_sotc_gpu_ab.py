#!/usr/bin/env python3
"""The user's already-enabled GPU renderer paths are permanent in Android 0.1.51."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
RUN=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
GAME=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
PACK=(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text()
class PermanentGpuPaths(unittest.TestCase):
    def test_enabled_modes_are_hardwired_not_switches(self):
        for flag,key in (("SOTC_FAST_BIND","sotc_fast_bind"),
                         ("SOTC_RECORD_THREAD","sotc_record_thread"),
                         ("SOTC_RB_ASYNC","sotc_rb_async"),
                         ("SOTC_ASYNC_SHADERS","sotc_async_shaders"),
                         ("SOTC_ASYNC_COMPUTE","sotc_async_compute")):
            self.assertIn("export "+flag+"=1",RUN)
            self.assertIn('env.put("'+flag+'","1");',GAME)
            self.assertNotIn('save("'+key+'",',UI)
            self.assertIn(key+"=1",PACK)
    def test_keep_real_gpu_work_and_user_patches(self):
        self.assertIn("export BB_READBACKS="+"${BB_READBACKS:-2}",RUN)
        self.assertIn("export SOTC_UPLOAD_BUDGET_MB=0",RUN)
        self.assertIn("export SOTC_ASYNC_TRANSLATE=0",RUN)
        for key in ("sotc_bachata_bloom","sotc_bachata_ssr",
                    "sotc_bachata_fog","sotc_bachata_shadows",
                    "sotc_blur_suppression"):
            self.assertIn('save("'+key+'",',UI)
        self.assertIn('save("sotc_perf_profile",',UI)
if __name__=="__main__":unittest.main()
