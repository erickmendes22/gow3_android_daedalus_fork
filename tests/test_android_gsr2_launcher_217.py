"""v2.1.7 Bionic Snapdragon GSR2 launcher-to-runtime contract."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
POPUP = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/feature/home/HomePopups.kt").read_text()
HOME = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/feature/home/HomeScreen.kt").read_text()
LAUNCH = (ROOT / "scripts/launch_env.py").read_text()
GPU = (ROOT / "gpu/shim/gow3_settings.cpp").read_text()
INI = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/data/Gow3Ini.kt").read_text()

class Gsr2Launcher217(unittest.TestCase):
    def test_bionic_home_exposes_selectable_provider(self):
        # Exactly ONE video/resolution entry opens the provider selector.
        self.assertNotIn('R.string.home_gsr2_summary_fmt', HOME)
        self.assertIn('HomeAction(stringResource(R.string.home_resolution_summary_fmt,', HOME)
        self.assertIn('popup = HomePopupKind.VIDEO', HOME)
        self.assertIn('OptionRow(stringResource(R.string.popup_gsr2_off), !gsr2)', POPUP)
        self.assertIn('OptionRow(stringResource(R.string.popup_gsr2_on), gsr2)', POPUP)

    def test_selection_saved_as_actual_runtime_keys(self):
        self.assertIn('mutableStateOf(ini["upscaler"] == "gsr2")', POPUP)
        self.assertIn('"upscaler" to (if (gsr2) "gsr2" else "off")', POPUP)
        self.assertIn('"preset" to "0"', POPUP)
        self.assertIn('"render_resolution" to resolution', POPUP)
        self.assertNotIn('if (gsr2) "720p" else resolution', POPUP)
        self.assertIn('Gow3Ini.write(gow3IniFile(context), values)', HOME)
        self.assertIn('pending.putAll(updates)', INI)
        self.assertIn("ini.get('upscaler') == 'gsr2'", LAUNCH)
        self.assertIn("updates['GOW3_UPSCALER'] = 'gsr2' if gsr2_requested else 'none'", LAUNCH)
        self.assertIn('{"off", "fsr3", "fsr4", "fsr411", "taa", "dlss", "gsr2"}', GPU)

    def test_spatial_filter_does_not_force_resolution_or_temporal_presets(self):
        self.assertIn('OptionRow(label, resolution == value) { resolution = value }', POPUP)
        self.assertIn('Every resolution remains available with GSR2 spatial', POPUP)
        self.assertIn('"preset" to "0"', POPUP)
        self.assertIn('GOW3_GSR2_SPATIAL_ONLY', LAUNCH)
        self.assertNotIn('if (!gsr2 || value == "720p")', POPUP)
        self.assertNotIn('resolution = "720p"', POPUP)

    def test_both_languages_contain_all_gsr2_strings(self):
        keys = (
            'home_gsr2_summary_fmt', 'popup_gsr2_title', 'popup_gsr2_off',
            'popup_gsr2_on', 'popup_gsr2_preset_title', 'popup_gsr2_native_aa',
            'popup_gsr2_quality', 'popup_gsr2_balanced', 'popup_gsr2_performance',
            'popup_gsr2_ultra_performance', 'popup_gsr2_720p_notice',
            'popup_gsr2_summary_off',
        )
        for locale in ('values', 'values-pt-rBR'):
            xml = ROOT / 'android-launcher/app/src/main/res' / locale / 'strings.xml'
            all_strings = {el.attrib['name']: el.text
                           for el in ET.parse(xml).getroot().findall('string')}
            for key in keys:
                with self.subTest(locale=locale, key=key):
                    self.assertIn(key, all_strings)
                    self.assertTrue(all_strings[key])
        self.assertIn('GOW3_GSR2_AUTO_PROBE', (
            ROOT / 'tools/android/bionic/run-bionic.sh').read_text())

if __name__ == '__main__':
    unittest.main()
