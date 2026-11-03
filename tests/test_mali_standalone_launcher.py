"""Keep the diagnostic Mali package on exactly the same Bionic runtime code path."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
HOME = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/feature/home/HomeScreen.kt").read_text()
GRADLE = (ROOT / "android-launcher/app/build.gradle.kts").read_text()

class MaliStandaloneRuntimeSelection(unittest.TestCase):
    def test_game_activity_launches_bionic_for_both_app_ids(self):
        fn = GAME.split("private boolean bionicRuntime()", 1)[1].split("private ", 1)[0]
        self.assertIn('"com.gow3.android.bionic".equals(packageName)', fn)
        self.assertIn('"com.gow3.android.bionic.malitest".equals(packageName)', fn)
        self.assertIn('if (bionicRuntime()) startBionic(holder)', GAME)

    def test_home_recognizes_standalone_as_bionic(self):
        self.assertIn('context.packageName == "com.gow3.android.bionic"', HOME)
        self.assertIn('context.packageName == "com.gow3.android.bionic.malitest"', HOME)
        self.assertIn('if (isBionic)', HOME)

    def test_package_remains_isolated(self):
        self.assertIn('applicationId = "com.gow3.android.bionic"', GRADLE)
        self.assertIn('applicationId = "com.gow3.android.bionic.malitest"', GRADLE)

if __name__ == "__main__":
    unittest.main()
