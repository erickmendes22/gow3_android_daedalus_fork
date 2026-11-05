"""Keep the Android-facing interface free of retired scaling controls."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AndroidDisplayTests(unittest.TestCase):
    def test_no_retired_feature_labels_in_localized_ui(self):
        for file in (
            "android-launcher/app/src/main/res/values/strings.xml",
            "android-launcher/app/src/main/res/values-zh-rCN/strings.xml",
            "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/SettingsDialog.java",
        ):
            with self.subTest(file=file):
                content = (ROOT / file).read_text(encoding="utf-8")
                self.assertNotIn("FSR", content.upper())
                self.assertNotIn("upscaler and replaces", content.lower())
        dialog = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/SettingsDialog.java").read_text()
        self.assertIn('heading(box,"Render resolution")', dialog)

    def test_native_overlay_does_not_offer_old_scaling_status(self):
        overlay = (ROOT / "gpu/shim/gow3_overlay.cpp").read_text()
        self.assertIn('std::getenv("GOW3_ANDROID_PORT") ? ~unsigned(P::Upscaler)', overlay)
        self.assertIn('if (item == 2 && std::getenv("GOW3_ANDROID_PORT")) continue;', overlay)
        self.assertNotIn("Needs FSR 1:", overlay)

    def test_runtime_messages_do_not_mention_retired_feature(self):
        launch = (ROOT / "tools/android/device/run-gow3.sh").read_text()
        self.assertNotIn("fsr=disabled", launch)
        self.assertNotIn("upscaler=${GOW3_UPSCALER", launch)
        self.assertIn('export GOW3_UPSCALER=none', launch)
        patches = (ROOT / "scripts/patches.py").read_text()
        self.assertNotIn("without FSR", patches)

    def test_quiet_pad_bridge_suppresses_logging_not_input(self):
        launcher = (ROOT / "tools/android/device/run-gow3.sh").read_text()
        pad = (ROOT / "src/runtime_pad.c").read_text()
        self.assertIn("GOW3_PAD_QUIET=1", launcher)
        self.assertIn('getenv("GOW3_PAD_QUIET")', pad)
        self.assertIn('strcmp(quiet, "1") != 0', pad)
        self.assertIn("last_buttons = injected.buttons;", pad)
        self.assertIn("memcpy(last_stick, injected.stick", pad)

if __name__ == "__main__":
    unittest.main()
