#!/usr/bin/env python3
"""SotC Vulkan recorder and async readback are independent, opt-in optimizations."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
RUN=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
GAME=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
PACK=(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text()


class ParallelPerformanceAB(unittest.TestCase):
    def test_each_path_can_be_enabled_and_disabled_independently(self):
        for var, key in (("SOTC_RECORD_THREAD","sotc_record_thread"),
                         ("SOTC_RB_ASYNC","sotc_rb_async")):
            self.assertIn("export "+var+"=${"+var+":-0}",RUN)
            self.assertIn('env.put("'+var+'",',GAME)
            self.assertIn('values["'+key+'"]?:"0"',UI)
            self.assertIn('save("'+key+'",if(it)"1" else "0")',UI)
            self.assertIn(key+"=0",PACK)
        self.assertIn("record_thread=$SOTC_RECORD_THREAD rb_async=$SOTC_RB_ASYNC",RUN)

    def test_existing_graphical_correctness_remains_conservative(self):
        for fragment in ("export BB_READBACKS=2",
                         "export SOTC_ASYNC_SHADERS=${SOTC_ASYNC_SHADERS:-0}",
                         "export SOTC_ASYNC_TRANSLATE=0",
                         "export SOTC_UPLOAD_BUDGET_MB=0",
                         "export SOTC_FAST_BIND=${SOTC_FAST_BIND:-0}"):
            self.assertIn(fragment,RUN)
        self.assertNotIn("export SOTC_RB_ASYNC=1",RUN)


if __name__=="__main__":
    unittest.main()
