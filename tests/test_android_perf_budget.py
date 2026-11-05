"""Android CPU/GPU overlap policy. Source checks; do not claim measured FPS."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AndroidPerfBudgetTests(unittest.TestCase):
    def test_direct_draw_does_not_start_unused_speculative_workers(self):
        draw = (ROOT / 'gpu/shadps4/video_core/renderer_vulkan/vk_draw_prep.cpp').read_text()
        start = draw.index('u32 DefaultWorkerCount() {')
        end = draw.index('\n}', start)
        policy = draw[start:end]
        self.assertIn('std::getenv("GOW3_PREP_WORKERS")', policy)
        self.assertIn('std::getenv("GOW3_ANDROID_PORT")', policy)
        self.assertRegex(policy, r'if \(std::getenv\("GOW3_ANDROID_PORT"\)\)\s*\{\s*return 0;')
        self.assertIn('return std::clamp<u32>(Gow3Threads::Available() / 2, 1, 8)', policy)
        self.assertIn('if (!Enabled())', draw)
        self.assertIn('return {};', draw)
        raster = (ROOT / 'gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp').read_text()
        self.assertIn('if (std::getenv("GOW3_ANDROID_PORT")) return false;', raster)

    def test_two_frames_in_flight_on_new_android_installs(self):
        ini = (ROOT / 'tools/android/config/gow3-default.ini').read_text()
        launch = (ROOT / 'android-launcher/app/src/main/java/com/gow3/android/data/LaunchParams.kt').read_text()
        self.assertIn('frames_queued=2', ini)
        setting = launch.split('key = "frames_queued"', 1)[1].split('descriptionRes', 1)[0]
        self.assertIn('defaultValue = "2"', setting)
        self.assertIn('LaunchOption("1"', setting)
        self.assertIn('LaunchOption("0"', setting)
        presenter = (ROOT / 'gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp').read_text()
        self.assertIn('Gow3Settings::Get().frames_queued.load()', presenter)
        self.assertIn('draw_scheduler.Wait(tick)', presenter)

    def test_existing_config_only_migrates_missing_queue_setting(self):
        import sys
        import tempfile
        from unittest.mock import patch
        sys.path.insert(0, str(ROOT / 'scripts'))
        import launch_env
        import patches

        profile = ({'CUSA01715'}, ROOT / 'patches/God_of_War_III_Remastered.xml',
                   '01.02', 'God of War III')
        status = {'title_id': 'CUSA01715', 'app_version': '01.02',
                  'eboot_sha256': patches.CUSA01715_0102_ANDROID_SHA,
                  'eboot_matches': True, 'reason': 'validated'}
        for configured in (None, '1', '2', '0'):
            with self.subTest(configured=configured), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                config = folder / 'gow3.ini'
                setting = f'frames_queued={configured}\n' if configured is not None else ''
                config.write_text('render_resolution=720p\n' + setting)
                with patch.object(patches, 'patch_profile_status', return_value=status), \
                        patch.object(patches, 'game_profile', return_value=profile):
                    launch_env.derive(folder, config, folder / 'state.json',
                                      {'GOW3_ANDROID_PORT': '1'})
                config_text = config.read_text()
                expected = '2' if configured is None else configured
                self.assertIn(f'frames_queued={expected}\n', config_text)
                self.assertEqual(config_text.count('frames_queued='), 1)

if __name__ == '__main__':
    unittest.main()
