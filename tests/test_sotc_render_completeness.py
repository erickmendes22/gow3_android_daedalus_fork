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

    def test_no_zero_filled_texture_placeholders_on_android(self):
        text = LAUNCHER.read_text()
        self.assertIn("export SOTC_UPLOAD_BUDGET_MB=0", text)
        self.assertLess(text.index("export SOTC_UPLOAD_BUDGET_MB=0"), text.index('exec "$@"'))
        self.assertIn("zero-fill upload deferral disabled", text)
        self.assertIn("export SOTC_RB_ASYNC=0", text)

    def test_real_texture_lod_streaming_starts_high_stable(self):
        text = LAUNCHER.read_text()
        # Verified in the 0.1.15 Android log: with linger 0, the renderer
        # reported "texture level off" (no fine mip streaming).
        self.assertIn('export SOTC_LOD_LINGER=${SOTC_LOD_LINGER:-1}', text)
        self.assertIn('export SOTC_LOD_LEVEL=${SOTC_LOD_LEVEL:-2}', text)
        self.assertIn('export SOTC_LOD_POOL_LOW=${SOTC_LOD_POOL_LOW:-8}', text)
        self.assertIn("SotC texture streaming: high/stable", text)
        self.assertLess(text.index('export SOTC_LOD_LINGER='), text.index('exec "$@"'))

    def test_dynamic_srt_offset_remains_shader_owned(self):
        text = SRT.read_text()
        self.assertIn("NeedsShaderDynamicOffset(src_off_dw) ||", text)
        self.assertIn("return (inst->Flags<u32>() & ReadConstDynamicWindowFlag) != 0;", text)
        self.assertIn("OpCopyWindow", text)

if __name__ == "__main__":
    unittest.main()
