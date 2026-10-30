#!/usr/bin/env python3
"""Ensure SotC APK cannot silently package an unbuilt GoW3 renderer."""
import ast
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class SotcPackageTest(unittest.TestCase):
    def test_bionic_payload_requires_bbgpu(self):
        path=ROOT/'ports/sotc/android/package_sotc_runtime.py'
        s=path.read_text()
        ast.parse(s)
        for needle in ('libbbgpu.so','com.sotc.android.daedalus',
                       'sotc-upstream/scripts','run-sotc-bionic.sh',
                       'sotc_prepare_game.py','LICENSE-ShadowOfTheColossus-PC.txt'):
            self.assertIn(needle,s)
        self.assertIn('if not renderer.is_file()',s)
if __name__=='__main__': unittest.main()
