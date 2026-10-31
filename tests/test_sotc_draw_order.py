#!/usr/bin/env python3
"""Guard SotC-only graphics draw ordering against split-thread vertex corruption."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "ports/sotc/android/run-sotc-bionic.sh"

class SotcDrawOrderTests(unittest.TestCase):
    def test_sync_command_processor_default(self):
        s = RUN.read_text()
        self.assertIn('export SOTC_CP_THREADS=${SOTC_CP_THREADS:-0}', s)
        self.assertIn('SotC GPU draw order: in-order command processor', s)
        self.assertIn('SotC GPU draw order: experimental split draw thread', s)
        self.assertLess(s.index('export SOTC_CP_THREADS='), s.index('exec "$@"'))
        self.assertIn('case "$SOTC_CP_THREADS" in', s)

    def test_do_not_discard_proven_visual_corrections(self):
        s = RUN.read_text()
        self.assertIn('export BB_READBACKS=2', s)
        self.assertIn('export SOTC_RB_ASYNC=0', s)
        self.assertIn('export SOTC_ANDROID_FRAGMENT_TSHARP=1', s)
        self.assertIn('export SOTC_TAA_OFF=${SOTC_TAA_OFF:-1}', s)
        self.assertIn('gpu-user-srt-phi4-barycentric-gs-', s)
        self.assertIn('export SOTC_ASYNC_SHADERS=0', s)
        self.assertNotIn('export SOTC_ADRENO_WAVE32=0', s)
        self.assertNotIn('export SOTC_INDIRECT_DIRECT=0', s)

if __name__ == "__main__":
    unittest.main()
