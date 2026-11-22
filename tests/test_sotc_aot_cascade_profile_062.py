#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Keep Android AOT compilation and gameplay sun-cascade image profiles identical."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class SotcAotCascadeProfile(unittest.TestCase):
    def test_aot_and_launch_both_forward_sun_cascade_mode(self):
        builder = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/data/SotcAotBuildManager.kt").read_text()
        launcher = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        script = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
        self.assertIn('val sunCascades = opt("sotc_sun_cascades", "5")', builder)
        self.assertIn('env["SOTC_SUN_CASCADES"] = sunCascades', builder)
        self.assertIn('env["SOTC_CVARS"] = cvars', builder)
        self.assertIn('env.put("SOTC_SUN_CASCADES",sunCascades);', launcher)
        self.assertIn('env.put("SOTC_CVARS",cvars);', launcher)
        self.assertIn('if [ "$SOTC_SUN_CASCADES" = "0" ]; then', script)
        self.assertIn('r_enableCascadeShadows=0', script)
        self.assertIn('--cvars "${SOTC_CVARS:-', script)
        self.assertIn('case "$SOTC_SUN_CASCADES" in', script)
        self.assertIn('export SOTC_SUN_CASCADES="${SOTC_SUN_CASCADES:-5}"', script)

    def test_runtime_script_syntax(self):
        script = str(ROOT / "ports/sotc/android/run-sotc-bionic.sh")
        result = subprocess.run(["bash","-n",script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__ == "__main__":
    unittest.main()
