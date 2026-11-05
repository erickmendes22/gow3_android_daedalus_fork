"""Run Android's no-SDL PadBridge logic using the real runtime implementation."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BionicPad(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'), 'C compiler required')
    def test_no_sdl_pad_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp)/'pad'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pthread','-I'+str(ROOT),
                            str(ROOT/'tests/test_pad_bionic.c'),'-o',str(binary)],
                           check=True, capture_output=True)
            run = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn('PASS: Bionic PadBridge ABI, triggers, touchpad and overlay capture', run.stdout)
