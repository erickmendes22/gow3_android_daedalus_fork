"""Mali-only APK must work without optional framegen, without weakening regular builds."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACK = (ROOT / "tools/android/bionic/package_runtime.py").read_text()
VALID = (ROOT / "tools/android/bionic/validate_apk.py").read_text()
BUILD = (ROOT / "tools/android/bionic/build_apk.sh").read_text()
SIGN = (ROOT / "tools/android/bionic/sign_apk.sh").read_text()
GRADLE = (ROOT / "android-launcher/app/build.gradle.kts").read_text()
INSTALL = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/RuntimeInstaller.java").read_text()
WORKFLOW = (ROOT / ".github/workflows/gow3-218-panvk-videoout-native.yml").read_text()

class MaliOnlyPackage(unittest.TestCase):
    def test_optional_bloodframe_omitted_only_in_mali_profile(self):
        self.assertIn("p.add_argument('--mali-only'", PACK)
        self.assertIn("if not a.mali_only:", PACK)
        self.assertIn("libs.append('libbloodframe.so')", PACK)
        self.assertIn("'bloodframe_bundled': not a.mali_only", PACK)
        self.assertIn("GOW3_MALI_ONLY_BUILD", BUILD)
        self.assertIn("package_args+=(--mali-only)", BUILD)
    def test_validator_keeps_regular_framegen_contract(self):
        self.assertIn("bloodframe_bundled = identity.get('bloodframe_bundled', True)", VALID)
        self.assertIn("if bloodframe_bundled:", VALID)
        self.assertIn("required.append('gow3port/arm64/lib/libbloodframe.so')", VALID)
        self.assertIn("Bloodframe native engine missing ELF signature", VALID)
        self.assertIn("Mali-only runtime unexpectedly bundles Bloodframe", VALID)

    def test_standalone_diagnostic_keeps_existing_app_and_saves_untouched(self):
        self.assertIn("GOW3_MALI_TEST_APK", BUILD)
        self.assertIn("gradle_args+=(-Pgow3MaliTest=true)", BUILD)
        self.assertIn("package_args+=(--mali-test)", BUILD)
        self.assertIn("standaloneMali", GRADLE)
        self.assertIn("com.gow3.android.bionic.malitest", GRADLE)
        self.assertIn("com.gow3.android.bionic.malitest", PACK)
        self.assertIn("com.gow3.android.bionic.malitest", INSTALL)
        self.assertIn("com.gow3.android.bionic.malitest", VALID)
        self.assertIn("GOW3_MALI_TEST_APK", SIGN)
        self.assertIn("tools/android/debug/gow3-debug.keystore", SIGN)
        self.assertIn("Build separately installable Mali diagnostic APK", WORKFLOW)

    def test_ci_skips_inaccessible_framegen_for_panvk(self):
        self.assertIn("GOW3_MALI_ONLY_BUILD: '1'", WORKFLOW)
        self.assertIn("if: env.GOW3_MALI_ONLY_BUILD != '1'", WORKFLOW)
        self.assertIn("Build and validate CPU, GPU and native runtime", WORKFLOW)
        self.assertIn("Check existing signing identity", WORKFLOW)

if __name__ == "__main__":
    unittest.main()
