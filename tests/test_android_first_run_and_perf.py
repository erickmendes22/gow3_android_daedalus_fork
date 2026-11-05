"""Regression checks for Android source selection and safe performance policy."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AndroidFirstRunAndPerfTests(unittest.TestCase):
    def test_first_run_offers_both_sources_and_skips_configured_games(self):
        activity = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/MainActivity.kt").read_text()
        self.assertIn('if (savedInstanceState == null || !hasStoragePermission())', activity)
        self.assertIn('if (!gameFolderManager.hasGameFolder()) showFirstRunGameSource()', activity)
        # First-run setup may only be offered after the original storage grant.
        setup = activity.split('private fun ensureInitialStorage()', 1)[1].split('private fun showFirstRunGameSource()', 1)[0]
        self.assertLess(setup.index('requestPermissions('), setup.index('showFirstRunGameSource()'))
        self.assertIn('REQUEST_INITIAL_STORAGE)', setup)
        self.assertIn('return', setup[:setup.index('showFirstRunGameSource()')])
        self.assertIn('showFirstRunGameSource()', activity)
        self.assertIn('setPositiveButton(getString(R.string.pkg_install))', activity)
        self.assertIn('pkgInstallManager.pickBasePkg()', activity)
        self.assertIn('setNegativeButton(getString(R.string.setup_folder))', activity)
        self.assertIn('gameFolderManager.chooseGameFolder()', activity)

    def test_external_storage_permission_is_compatible_with_android_11(self):
        picker = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/data/GameFolderManager.kt").read_text()
        manifest = (ROOT / "android-launcher/app/src/main/AndroidManifest.xml").read_text()
        self.assertIn('Build.VERSION.SDK_INT >= Build.VERSION_CODES.R', picker)
        self.assertIn('Environment.isExternalStorageManager()', picker)
        self.assertIn('Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION', picker)
        self.assertIn('REQUEST_ALL_FILES_FOLDER = 1013', picker)
        self.assertNotIn('if (kind == Kind.GAME) ensureGameFolder()', picker)
        self.assertIn('CUSA01715', picker)
        self.assertIn('android.permission.MANAGE_EXTERNAL_STORAGE', manifest)

    def test_guest_direct_output_skips_unused_compute_pipelines(self):
        presenter = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text()
        self.assertIn('if (!std::getenv("GOW3_ANDROID_PORT")) {\n        fsr_pass.Create', presenter)
        self.assertIn('if (!native_android) {\n        image_view = fsr_pass.Render', presenter)
        self.assertIn('!native_android && graphics.fsr1', presenter)
        self.assertIn('!native_android && graphics.rcas', presenter)

    def test_readback_and_affinity_cannot_be_disabled_unsafely(self):
        cache = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()
        self.assertIn('scheduler.Wait(tick)', cache)
        self.assertIn('scheduler.Finish()', cache)
        self.assertIn('pending_readbacks.RequiredTick', cache)
        threads = (ROOT / "src/runtime_thread.c").read_text()
        self.assertIn('static ABI int32_t attr_set_affinity', threads)
        self.assertIn('t->attr.prio=prio', threads)

if __name__ == "__main__":
    unittest.main()
