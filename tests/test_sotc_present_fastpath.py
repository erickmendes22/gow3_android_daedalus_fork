#!/usr/bin/env python3
"""0.1.25: AHB full-blit optimization and isolated compute worker tests."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = (ROOT / "ports/sotc/android/stage_present_full_blit.py").read_text()
WIRE = (ROOT / "ports/sotc/android/wire_ahb.py").read_text()
RUN = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
GAME = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
PACKAGE = (ROOT / "ports/sotc/android/package_sotc_runtime.py").read_text()


class SotcPresentFastpathTest(unittest.TestCase):
    def test_presenter_preserves_clears_for_every_partial_image(self):
        self.assertIn("from stage_present_full_blit import patch_present_full_blit", WIRE)
        self.assertLess(WIRE.index("presenter.write_text(content)"),
                        WIRE.index("patch_present_full_blit(gpu)"))
        for fragment in (
                "rect.offset.x != 0", "rect.offset.y != 0",
                "rect.extent.width != extent.width",
                "rect.extent.height != extent.height",
                "if (needs_black_clear) {",
                "clear_to_blit", "cmdbuf.clearColorImage(",
                'std::getenv("SOTC_PRESENT_FULL_BLIT")'):
            self.assertIn(fragment, STAGE)
        self.assertIn("refusing ambiguous clear/barrier patch", STAGE)
        self.assertIn("s.count(old_rect) != 1", STAGE)

    def test_compute_and_present_opt_outs_are_independent(self):
        self.assertIn("export SOTC_ASYNC_SHADERS=$"+"{SOTC_ASYNC_SHADERS:-0}", RUN)
        self.assertIn("export SOTC_ASYNC_COMPUTE=$"+"{SOTC_ASYNC_COMPUTE:-0}", RUN)
        self.assertIn("export SOTC_PRESENT_FULL_BLIT=$"+"{SOTC_PRESENT_FULL_BLIT:-1}", RUN)
        for env,key,default in (
                ("SOTC_ASYNC_COMPUTE","sotc_async_compute","0"),
                ("SOTC_PRESENT_FULL_BLIT","sotc_present_full_blit","1")):
            self.assertIn('env.put("'+env+'",', GAME)
            self.assertIn('save("'+key+'",if(it)"1" else "0")', UI)
            self.assertIn(key+"="+default, PACKAGE)
        self.assertIn("export BB_READBACKS=${BB_READBACKS:-2}", RUN)
        self.assertIn("export SOTC_ASYNC_TRANSLATE=0", RUN)
        self.assertIn("export SOTC_ASYNC_PRELOAD=0", RUN)
        self.assertIn("export SOTC_UPLOAD_BUDGET_MB=0", RUN)
        self.assertIn("experimental async graphics pipeline build", RUN)
        self.assertIn("synchronous graphics shaders and pipelines", RUN)

if __name__ == "__main__":
    unittest.main()
