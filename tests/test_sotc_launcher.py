#!/usr/bin/env python3
from pathlib import Path
import unittest
SCRIPT=Path(__file__).resolve().parents[1]/'ports/sotc/android/run-sotc-bionic.sh'
class SotcLauncherTest(unittest.TestCase):
    def test_sotc_files_and_not_gow3_prepare(self):
        s=SCRIPT.read_text()
        for needle in ('sotc_prepare_game.py','boot-linked.bin','content.bin','sotc-cpu.bin','--sotc-cmdline','libbbgpu.so','SOTC_PRESENT_SOCKET','GOW3_VULKAN_DRIVER'):
            self.assertIn(needle,s)
        self.assertNotIn('"$runtime/bin/gow3-prepare"',s)
if __name__=='__main__': unittest.main()
