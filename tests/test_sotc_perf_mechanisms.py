#!/usr/bin/env python3
"""Guard full GPU sync and permanent parallel copy/recording features."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
RUN=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
GAME=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
class PermanentParallelism(unittest.TestCase):
    def test_core_parallelism_enabled(self):
        for env,key in (("SOTC_RECORD_THREAD","sotc_record_thread"),
                        ("SOTC_RB_ASYNC","sotc_rb_async"),
                        ("SOTC_RB_STREAM","sotc_rb_stream")):
            self.assertIn('env.put("'+env+'","1");',GAME)
            self.assertIn("export "+env+"=1",RUN)
            self.assertNotIn('save("'+key+'",',UI)
        self.assertIn('env.put("SOTC_STAGING_LARGE_POW2","1");',GAME)
        self.assertIn('env.put("SOTC_BUF_ASYNC_KB","256");',GAME)
        self.assertIn("export SOTC_STAGING_LARGE_KEEP_MB=128",RUN)
    def test_no_replaced_memory_guards(self):
        self.assertIn("export SOTC_UPLOAD_BUDGET_MB=0",RUN)
        self.assertIn("export SOTC_ASYNC_TRANSLATE=0",RUN)
        self.assertIn("export BB_READBACKS="+"${BB_READBACKS:-2}",RUN)
        self.assertIn('if [ "$BB_READBACKS" != "2" ]; then export SOTC_RB_STREAM=0; fi',RUN)
if __name__=="__main__":unittest.main()
