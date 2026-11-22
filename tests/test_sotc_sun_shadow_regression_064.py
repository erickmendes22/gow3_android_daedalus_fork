#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shadow regression A/B: 0 engine-only, no thousands of Vulkan clears."""
from pathlib import Path
import re
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_sotc_sun_shadow_cascades_059 import CPP

class Regressions(unittest.TestCase):
    def test_keep_zero_fails_open_before_all_depth_operations(self):
        start = CPP.index("    if (keep == 0) {")
        end = CPP.index("    if (keep >= 5) return false;", start)
        block=CPP[start:end]
        self.assertIn("return false;",block)
        self.assertIn("SOTC SUN ENGINE ONLY:",block)
        self.assertNotIn("clearDepthStencilImage",block)
        self.assertNotIn("FindRenderTarget",block)
        self.assertNotIn("EndRendering",block)
        self.assertLess(end, CPP.index("const auto guard = texture_cache.BatchLock()"))
        self.assertLess(end, CPP.index("scheduler.EndRendering();"))

    def test_compilation_and_launch_cvars_identical(self):
        script=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
        self.assertIn('if [ "$SOTC_SUN_CASCADES" = "0" ]; then',script)
        self.assertIn('r_enableCascadeShadows=0',script)
        self.assertIn('--cvars "${SOTC_CVARS:-',script)
        aot=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/data/SotcAotBuildManager.kt").read_text()
        self.assertIn('env["SOTC_SUN_CASCADES"] = sunCascades',aot)
        launch=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        self.assertIn('env.put("SOTC_SUN_CASCADES",sunCascades);',launch)

    def test_no_unmeasured_empty_indirect_fastpath_in_launcher_or_staging(self):
        stage=(ROOT/"ports/sotc/android/stage_renderer.py").read_text()
        ui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        launch=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        for src in (stage,ui,launch):
            self.assertNotIn("SOTC_INDIRECT_EMPTY_BIND",src)
            self.assertNotIn("sotc_indirect_empty_bind_063",src)
        self.assertNotIn("patch_indirect_empty",stage)

if __name__ == "__main__":
    unittest.main()
