"""Arena expansion and startup fix are independent of resolution and effect selection."""
import unittest
import xml.etree.ElementTree as ET
import contextlib
import io
from unittest import mock

import paths
import graphics_options as graphics
import patches
import launch_env
from test_launch_env import LaunchEnvReasonTests

XML = paths.ROOT / 'patches/God_of_War_III_Remastered.xml'


class ArenaPatchTests(unittest.TestCase):
    def test_only_arena_operand_is_removed_at_every_resolution(self):
        for resolution in ('480p', '720p', '900p', '1440p', '1800p', '4K'):
            with self.subTest(resolution=resolution):
                names = ['Resolution Patch - ' + resolution]
                expanded = patches.compile_patches(XML, names, '01.02', [(0, 0x4000000)])
                original = patches.compile_patches(XML, names, '01.02', [(0, 0x4000000)],
                                                   expand_video_arena=False)
                arena = 0x007cd918 - patches.EBOOT_BASE
                self.assertEqual(original, [(a, b) for a, b in expanded if a != arena])
                self.assertEqual(len(expanded) - len(original), 1)

    def test_native_arena_fix_is_not_reinserted_when_disabled(self):
        options = graphics.startup_options({'expand_video_arena': '0', 'engine_fps': '60'})
        self.assertEqual(graphics.patch_names([graphics.TEXTURE_FIX], options), [])

    def test_startup_fix_is_not_forced_back_into_explicit_selection(self):
        names = patches.selected_patches(XML, '01.02', '', only=True,
                                         startup_black_screen=False)
        self.assertNotIn('Bug Fix - Startup Black Screen', names)
        self.assertIn('Bug Fix - Startup Black Screen',
                      patches.selected_patches(XML, '01.02', '', only=True))

    def test_legacy_catalog_retains_exact_write_bytes(self):
        # Attributes separate the policy; the existing arena values remain unchanged.
        tagged = [line for line in ET.parse(XML).iter('Line')
                  if line.get('VideoArena') == 'true']
        self.assertEqual(len(tagged), 7)
        self.assertEqual({line.get('Address') for line in tagged}, {'0x007cd918'})


class ArenaLaunchTests(LaunchEnvReasonTests):
    def test_empty_explicit_selection_does_not_restore_xml_defaults(self):
        self.config.write_text('render_resolution=native\nengine_fps=60\nexpand_video_arena=0\n'
                               'patch_startup_black_screen=0\npatch_skip_video=0\n')
        plan = self._plan({'GOW3_ANDROID_PORT': '1'})
        self.assertEqual(plan['patch_names'], [])
        output = io.StringIO()
        with mock.patch.object(launch_env, 'derive', return_value=plan), contextlib.redirect_stdout(output):
            launch_env.main(['--game', str(self.dir / 'game'), '--config', str(self.config),
                             '--state', str(self.state), '--shell'])
        self.assertIn("export GOW3_PATCHES_ONLY='1'", output.getvalue())
        self.assertIn("export GOW3_PATCHES=''", output.getvalue())

    def test_disabled_expansion_keeps_4k_fps_and_effects_selected(self):
        self.config.write_text('render_resolution=4K\nengine_fps=240\nexpand_video_arena=0\n'
                               'patch_startup_black_screen=0\npatch_disable_ssao=1\n')
        plan = self._plan({'GOW3_ANDROID_PORT': '1', 'GOW3_DEVICE_MEM_MB': '10500'})
        self.assertEqual(plan['updates']['GOW3_PATCH_STATUS'], 'validated')
        self.assertEqual(plan['updates']['GOW3_EXPAND_VIDEO_ARENA'], '0')
        self.assertEqual(plan['updates']['GOW3_STARTUP_BLACK_SCREEN'], '0')
        self.assertEqual(plan['dmem'], 5056)
        self.assertEqual(plan['vblank'], 240)
        for name in ('Resolution Patch - 4K', 'Frame Rate Patch - 240 FPS', 'Disable SSAO'):
            self.assertIn(name, plan['patch_names'])
        self.assertNotIn(graphics.TEXTURE_FIX, plan['patch_names'])
        self.assertNotIn('Bug Fix - Startup Black Screen', plan['patch_names'])


if __name__ == '__main__':
    unittest.main()
