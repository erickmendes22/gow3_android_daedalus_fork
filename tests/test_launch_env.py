import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paths  # noqa: F401  (puts scripts/ on sys.path)
import patches
from launch_env import derive

GOW3_XML = paths.ROOT / 'patches/God_of_War_III_Remastered.xml'


def _validated_profile():
    """A fake validated CUSA01623 profile (no hash: derive does not need to read eboot)."""
    return ({'CUSA01623'}, GOW3_XML, '01.02', None, None)


class LaunchEnvReasonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.config = self.dir / 'gow3.ini'
        self.state = self.dir / 'state.json'

    def tearDown(self):
        self.temp.cleanup()

    def _plan(self, env=None):
        env = dict(env or {})
        with mock.patch.object(patches, 'patch_profile_status',
                               return_value={'title_id': 'CUSA01623', 'app_version': '01.02',
                                             'supported': True, 'eboot_sha256': 'x',
                                             'eboot_matches': True, 'patch_sites_match': True,
                                             'reason': 'validated'}):
            with mock.patch.object(patches, 'game_profile', return_value=_validated_profile()):
                return derive(self.dir / 'game', self.config, self.state, env)

    def test_validated_default_patch_set_and_reason(self):
        plan = self._plan()
        self.assertEqual(plan['updates']['GOW3_PATCH_STATUS'], 'validated')
        self.assertIn('Bug Fix - Texture Corruption Fix', plan['patch_names'])

    def test_patch_conflict_reason_and_no_patches(self):
        # Two resolution patches are exclusive: select none and report the conflict.
        plan = self._plan({'GOW3_PATCHES': 'Resolution Patch - 4K;Resolution Patch - 720p',
                           'GOW3_PATCHES_ONLY': '1'})
        self.assertEqual(plan['updates']['GOW3_PATCH_STATUS'], 'patch-conflict')
        self.assertEqual(plan['patch_names'], [])
        self.assertIsNone(plan['dmem'])

    def test_insufficient_memory_budget_reason_and_no_patches(self):
        # The resolution patch needs 11200 MiB; a 4 GB device cannot hold it.
        plan = self._plan({'GOW3_PATCHES': 'Resolution Patch - 4K', 'GOW3_PATCHES_ONLY': '1',
                           'GOW3_DEVICE_MEM_MB': '4096'})
        self.assertEqual(plan['updates']['GOW3_PATCH_STATUS'], 'insufficient-memory-budget')
        self.assertEqual(plan['patch_names'], [])
        self.assertIsNone(plan['dmem'])

    def test_memory_budget_is_ignored_when_no_device_value(self):
        plan = self._plan({'GOW3_PATCHES': 'Resolution Patch - 4K', 'GOW3_PATCHES_ONLY': '1'})
        self.assertEqual(plan['updates']['GOW3_PATCH_STATUS'], 'validated')
        self.assertIsNotNone(plan['dmem'])

    def test_bionic_8gib_policy_uses_physical_memory_and_preserves_guest_budget(self):
        bionic = {'GOW3_ANDROID_PORT': '1', 'GOW3_BIONIC_RUNNER': '/app/run-bionic.sh'}
        for mib, expected in [('6144', False), ('7167', False), ('7168', True),
                              ('7297', True), ('8192', True), ('9216', True),
                              ('9217', False), ('11000', False), ('invalid', False)]:
            with self.subTest(mib=mib):
                plan = self._plan(dict(bionic, GOW3_DEVICE_MEM_MB=mib))
                normal = self._plan({'GOW3_ANDROID_PORT': '1', 'GOW3_DEVICE_MEM_MB': mib})
                self.assertEqual('GOW3_ANDROID_8GB_MEMORY' in plan['updates'], expected)
                self.assertEqual(plan['dmem'], normal['dmem'])
        desktop = self._plan({'GOW3_DEVICE_MEM_MB': '8192'})
        self.assertNotIn('GOW3_ANDROID_8GB_MEMORY', desktop['updates'])
        glibc = self._plan({'GOW3_ANDROID_PORT': '1', 'GOW3_DEVICE_MEM_MB': '8192'})
        self.assertNotIn('GOW3_ANDROID_8GB_MEMORY', glibc['updates'])

    def test_android_effect_toggles_preserve_home_resolution_and_mandatory_fixes(self):
        self.config.write_text('render_resolution=720p\nengine_fps=120\npatch_disable_ssao=1\npatch_skip_video=0\n')
        plan = self._plan({'GOW3_ANDROID_PORT': '1'})
        self.assertIn('Disable SSAO', plan['patch_names'])
        self.assertIn('Resolution Patch - 720p', plan['patch_names'])
        self.assertIn('Frame Rate Patch - 120 FPS', plan['patch_names'])
        self.assertIn('Bug Fix - Startup Black Screen', plan['patch_names'])
        self.assertNotIn('Skip Any Video With X Button', plan['patch_names'])
        self.assertIn('render_resolution=720p', self.config.read_text())
        desktop = self._plan()
        self.assertNotIn('Disable SSAO', desktop['patch_names'])

    def test_player_files_remain_byte_identical(self):
        game = self.dir / 'game'
        (game / 'sce_sys').mkdir(parents=True)
        eboot = game / 'eboot.bin'
        eboot.write_bytes(b'retail game image bytes' * 100)
        before = eboot.read_bytes()
        self._plan({'GOW3_PATCHES': 'Resolution Patch - 4K', 'GOW3_PATCHES_ONLY': '1'})
        self.assertEqual(eboot.read_bytes(), before)
        self.assertFalse((game / 'sce_sys' / 'param.sfo').exists())


if __name__ == '__main__':
    unittest.main()
