"""Regression: 2.1.7 launcher text must respect English / Portuguese selection."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android-launcher/app/src/main/java"
RES = ROOT / "android-launcher/app/src/main/res"

SOURCES = (
    "com/gow3/android/feature/home/HomeScreen.kt",
    "com/gow3/android/feature/home/HomePopups.kt",
    "com/gow3/android/feature/settings/GeneralSettingsScreen.kt",
    "com/gow3/android/feature/home/FrameGenerationCard.kt",
    "com/gow3/android/ui/LauncherScreen.kt",
)
NAMESPACES = ("home_", "popup_", "settings_", "framegen_", "nav_settings")
# English is the base locale; pt-BR must override the exact same new keys.
PLACEHOLDER = re.compile(r"%(?:[1-9][0-9]*\\$)?[dsf]")

def resources(locale):
    file = RES / locale / "strings.xml"
    root = ET.parse(file).getroot()
    return {e.attrib["name"]: "".join(e.itertext()) for e in root.findall("string")}

class LauncherLanguage217(unittest.TestCase):
    def test_base_and_ptbr_have_all_new_strings(self):
        base, pt = resources("values"), resources("values-pt-rBR")
        names = {k for k in base if k.startswith(NAMESPACES)}
        self.assertGreaterEqual(len(names), 70)
        self.assertEqual(names, {k for k in pt if k.startswith(NAMESPACES)})
        for name in names:
            self.assertTrue(base[name].strip(), name)
            self.assertTrue(pt[name].strip(), name)
            self.assertEqual(PLACEHOLDER.findall(base[name]),
                             PLACEHOLDER.findall(pt[name]), name)

    def test_every_ui_resource_reference_exists_in_both_languages(self):
        base, pt = resources("values"), resources("values-pt-rBR")
        for path in SOURCES:
            content = (JAVA / path).read_text(encoding="utf-8")
            for name in re.findall(r"R\\.string\\.([A-Za-z0-9_]+)", content):
                self.assertIn(name, base, (path, name))
                if name.startswith(NAMESPACES):
                    self.assertIn(name, pt, (path, name))

    def test_no_hardcoded_portuguese_labels_in_new_ui(self):
        for path in SOURCES:
            content = (JAVA / path).read_text(encoding="utf-8")
            # Literal accents in UI strings indicate text that bypasses resources.
            literals = re.findall(r'"[^"\\n]*[ãõçáéíóúàâêôÃÕÇÁÉÍÓÚÀÂÊÔ][^"\\n]*"', content)
            self.assertEqual([], literals, path)

    def test_language_override_recreates_with_english_or_ptbr_configuration(self):
        main = (JAVA / "com/gow3/android/MainActivity.kt").read_text(encoding="utf-8")
        manager = (JAVA / "com/gow3/android/data/LanguageManager.kt").read_text(encoding="utf-8")
        self.assertIn("super.attachBaseContext(applyLanguage(newBase))", main)
        self.assertIn("config.setLocale(LanguageManager.resolve(base))", main)
        self.assertIn("LanguageManager.set(this, value)", main)
        self.assertIn("recreate()", main)
        self.assertIn('PT -> Locale("pt", "BR")', manager)
        self.assertIn("else -> Locale.ENGLISH", manager)

    def test_kotlin_popups_read_localized_errors_not_cached_locale_literals(self):
        popups = (JAVA / SOURCES[1]).read_text(encoding="utf-8")
        self.assertIn("context.getString(R.string.popup_mods_imported_fmt, it)", popups)
        self.assertIn("context.getString(R.string.popup_mods_install_failed)", popups)
        self.assertIn("stringResource(R.string.popup_cheat_warning)", popups)
        self.assertIn("stringResource(label)", popups)

if __name__ == "__main__":
    unittest.main()
