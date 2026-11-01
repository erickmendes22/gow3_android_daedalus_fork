#!/usr/bin/env python3
"""Regression tests for Android OS symlink aliases and malicious nested redirects."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import sys
import unittest

source = Path(sys.argv[1]) if len(sys.argv)>1 else Path('order-source/scripts/order1886_mods.py')
spec = importlib.util.spec_from_file_location('order1886_mods_android_test',source)
mods = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mods)

class PathPolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.real=self.root/'real';self.real.mkdir()
        self.alias=self.root/'android_os_alias'
        self.alias.symlink_to(self.real,target_is_directory=True)
        self.game=self.alias/'games'/'CUSA00076';self.game.mkdir(parents=True)
        self.state=self.alias/'private'/'order1886';self.state.mkdir(parents=True)
        previous=dict(os.environ)
        self.addCleanup(lambda:(os.environ.clear(),os.environ.update(previous)))
        os.environ['ORDER1886_ANDROID_TRUSTED_GAME_ROOT']=str(self.game)
        os.environ['ORDER1886_ANDROID_TRUSTED_STATE_ROOT']=str(self.state)

    def test_trusted_mount_alias_accepts_game_and_private_state(self):
        self.assertEqual(mods.safe_path(self.game),self.game.resolve())
        self.assertEqual(mods.safe_path(self.state/'prepared'/'boot-linked.bin'),
                         (self.state/'prepared'/'boot-linked.bin').resolve())

    def test_symlink_under_game_is_denied(self):
        other=self.root/'outside';other.mkdir()
        (self.game/'_data').symlink_to(other,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Links and reparse points'):
            mods.safe_path(self.game/'_data'/'asset.bin')

    def test_symlink_under_state_is_denied(self):
        (self.state/'prepared').symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'Links and reparse points'):
            mods.safe_path(self.state/'prepared'/'boot-linked.bin')

    def test_unselected_alias_still_denied(self):
        outsider=self.alias/'other';outsider.mkdir()
        with self.assertRaisesRegex(ValueError,'Links and reparse points'):
            mods.safe_path(outsider)

    def test_without_android_roots_desktop_policy_is_unchanged(self):
        os.environ.pop('ORDER1886_ANDROID_TRUSTED_GAME_ROOT')
        os.environ.pop('ORDER1886_ANDROID_TRUSTED_STATE_ROOT')
        with self.assertRaisesRegex(ValueError,'Links and reparse points'):
            mods.safe_path(self.game)

if __name__=='__main__':
    unittest.main(argv=[sys.argv[0]],verbosity=2)
