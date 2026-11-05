"""Source contract: PS4 PKGs must not be copied or extracted to staging folders."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "android-launcher/app/src/main/java/com/gow3/android/data/PkgInstallManager.kt"
MANIFEST = ROOT / "android-launcher/app/src/main/AndroidManifest.xml"
MAIN = ROOT / "android-launcher/app/src/main/java/com/gow3/android/MainActivity.kt"


class AndroidPkgDirectTests(unittest.TestCase):
    def test_user_selects_original_file_and_destination(self):
        source = PKG.read_text()
        self.assertIn("Intent.ACTION_OPEN_DOCUMENT", source)
        self.assertIn("Intent.ACTION_OPEN_DOCUMENT_TREE", source)
        self.assertIn("REQUEST_BASE_DIRECTORY", source)
        self.assertIn("REQUEST_UPDATE_DIRECTORY", source)
        self.assertIn('listOf("info", pkg.canonicalPath)', source)
        self.assertIn('"--output", dest.canonicalPath', source)

    def test_no_copied_pkg_or_staging_folder(self):
        source = PKG.read_text()
        self.assertNotIn("openInputStream(", source)
        self.assertNotIn("input.outputStream(", source)
        self.assertNotIn('".input-"', source)
        self.assertNotIn('".stage-"', source)
        self.assertNotIn('".old-"', source)
        self.assertNotIn("stage.renameTo(", source)
        self.assertIn("dest.listFiles()", source)

    def test_updates_use_selected_base_and_validate_title_before_extraction(self):
        source = PKG.read_text()
        self.assertIn("replacingUpdate", source)
        self.assertIn('arguments.add("--force")', source)
        self.assertIn('"update_dir"', source)
        self.assertIn('"game_dir"', source)
        self.assertIn('baseTitle != title', source)
        self.assertIn('selectedDestination = Uri.fromFile(base)', source)
        self.assertIn('if (update) edit.remove("update_dir")', source)
        self.assertLess(source.index('if (baseTitle != title)'), source.index('execute(loader, helper, arguments, dest)'))
        self.assertIn('dest.canonicalFile', source)

    def test_direct_filesystem_permission_and_launcher(self):
        self.assertIn("MANAGE_EXTERNAL_STORAGE", MANIFEST.read_text())
        source = PKG.read_text()
        self.assertIn("ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION", source)
        self.assertIn('destination =', source.lower().replace('val destination', 'destination ='))
        main = MAIN.read_text()
        self.assertIn("pkgInstallManager.onPickerResult", main)


if __name__ == "__main__":
    unittest.main()
