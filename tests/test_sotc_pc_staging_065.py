#!/usr/bin/env python3
"""Regression guard for the real PC v0.76 staging-cache backport on Android."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ports/sotc/android/stage_sotc_pc_streaming_051.py"
LAUNCH = ROOT / "ports/sotc/android/run-sotc-bionic.sh"

class Pc076MobileStaging(unittest.TestCase):
    def test_stage_python_compiles_and_backports_real_pc_copy_path(self):
        ast.parse(SCRIPT.read_text())
        s = SCRIPT.read_text()
        self.assertIn('26e742030b0', s)
        self.assertIn('BbCopy::Async', s)
        self.assertIn('JoinAsyncUploads();', s)
        self.assertIn('scheduler.IsFree(entry.tick)', s)
        self.assertIn('SOTC_STAGING_LARGE_KEEP_MB', s)

    def test_auto_cap_and_user_override_are_safe(self):
        s = SCRIPT.read_text()
        self.assertIn('#include <unistd.h>', s)
        self.assertIn('sysconf(_SC_PHYS_PAGES)', s)
        self.assertIn('sysconf(_SC_PAGESIZE)', s)
        self.assertIn('fallback_mb = 128', s)
        self.assertIn('fallback_mb = 256', s)
        self.assertIn('(10ULL << 30)', s)
        self.assertIn("v[0] != 'a'", s)
        self.assertIn('std::strtoull(v, nullptr, 10)', s)
        run = LAUNCH.read_text()
        # PC 0.74 has its own numeric parser, unlike the newer 0.76
        # mobile auto-policy staged only for the old GPU revision.
        staged = (ROOT / "ports/sotc/android/stage_renderer.py").read_text()
        if "pc074_exact_fastpaths" in staged:
            self.assertIn('export SOTC_STAGING_LARGE_KEEP_MB=${SOTC_STAGING_LARGE_KEEP_MB:-128}', run)
            self.assertNotIn('SOTC_STAGING_LARGE_KEEP_MB:-auto', run)
        else:
            self.assertIn('export SOTC_STAGING_LARGE_KEEP_MB=${SOTC_STAGING_LARGE_KEEP_MB:-auto}', run)
        self.assertNotIn('export SOTC_STAGING_LARGE_KEEP_MB=128', run)

    def test_no_dangerous_optimizations_return(self):
        stage = (ROOT / "ports/sotc/android/stage_renderer.py").read_text()
        self.assertIn('patch_pc_streaming(out)', stage)
        self.assertNotIn('patch_indirect_empty(out)', stage)
        self.assertIn('patch_sun_cascades(out)', stage)

if __name__ == "__main__":
    unittest.main()
