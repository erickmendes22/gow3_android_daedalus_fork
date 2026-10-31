#!/usr/bin/env python3
"""Android render mode must not drop visible geometry while compiling shaders."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ports/sotc/android/run-sotc-bionic.sh"
SRT = ROOT / "ports/sotc/android/stage_srt_arm64.py"

class SotcRenderCompletenessTest(unittest.TestCase):
    def test_android_disables_skipping_draws(self):
        text = LAUNCHER.read_text()
        for name in ("SOTC_ASYNC_SHADERS", "SOTC_ASYNC_TRANSLATE", "SOTC_ASYNC_PRELOAD"):
            self.assertRegex(text, rf"(?m)^export {name}=0$")
        self.assertIn("no async draw skips", text)
        self.assertLess(text.index("export SOTC_ASYNC_SHADERS=0"), text.index('exec "$@"'))

    def test_dynamic_srt_offset_remains_shader_owned(self):
        text = SRT.read_text()
        self.assertIn("NeedsShaderDynamicOffset(src_off_dw) ||", text)
        self.assertIn("return (inst->Flags<u32>() & ReadConstDynamicWindowFlag) != 0;", text)
        self.assertIn("OpCopyWindow", text)

if __name__ == "__main__":
    unittest.main()
