"""2.1.7 Bionic release contract: home selection, mod load, eboot-verified 8K.

This test is static/host-side; it does NOT constitute on-device 8K or cheat
gameplay validation. 8K is rejected during Android preparation unless the
selected eboot meets the upstream byte signatures and known SHA-256.
"""
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT/path).read_text(encoding="utf-8")

class Release217(unittest.TestCase):
    def test_version(self):
        gradle=read("android-launcher/app/build.gradle.kts")
        self.assertIn('versionName = "2.1.7-bionic"', gradle)
        self.assertIn('versionCode = 2010700', gradle)
        # Every runtime/packaging check must use the same release name.
        # The first 2.1.7 APK compiled and signed, then failed here because
        # validate_apk.py, sign_apk.sh and package_runtime.py still said 2.1.6.
        expected = "2.1.7-bionic"
        validator = read("tools/android/bionic/validate_apk.py")
        signer = read("tools/android/bionic/sign_apk.sh")
        packager = read("tools/android/bionic/package_runtime.py")
        self.assertIn("versionName='" + expected + "'", validator)
        self.assertIn("God-of-War-III-Daedalus-Fork-v" + expected + "-arm64.apk", signer)
        self.assertIn("'version':'" + expected + "'", packager)
        self.assertIn("'runtime_name':'daedalus-gow3-bionic-2.1.7'", packager)
        self.assertNotIn("2.1.6-daedalus.4-bionic", validator + signer + packager)

    def test_8k_strict_eboot_signatures(self):
        xml=ET.parse(ROOT/"patches/God_of_War_III_Remastered.xml").getroot()
        patch=next(m for m in xml.iter("Metadata") if m.attrib.get("Name") == "Resolution Patch - 8K")
        entries=patch.find("PatchList").findall("Line")
        self.assertEqual(len(entries), 16)
        self.assertTrue(all(e.get("Pattern") and e.get("Address") and e.get("At")
                            for e in entries))
        expected={(int(x,16)) for x in (
            '0x0055a876','0x005f0b3b','0x005f0b43','0x005f0b4c','0x005f0b53',
            '0x005643f3','0x00564400','0x005ff769','0x005ff76f','0x007c46b4',
            '0x007c46b8','0x0056bb82','0x0060953d','0x007f2a3c','0x007f2a40','0x007cd918')}
        self.assertEqual({int(e.get("Address"),16) for e in entries},expected)
        self.assertEqual(next(e.get("Value") for e in entries if e.get("Address") == '0x0055a876'), "9090")
        patcher=read("scripts/patches.py")
        self.assertIn("if sha != REFERENCE_SHA256:", patcher)
        self.assertIn("if 'Resolution Patch - 8K' in skipped:",patcher)
        self.assertIn("expected.issubset(actual)",patcher)
        runner=read("tools/android/bionic/run-bionic.sh")
        self.assertIn('if [ "$(setting render_resolution)" = 8K ]; then',runner)
        self.assertIn('8K EXPERIMENTAL: eboot/available RAM not validated',runner)
        self.assertIn("'8K'",read("scripts/graphics_options.py"))
        self.assertIn('"8K"',read("gpu/shim/gow3_graphics.h"))

    def test_home_popup_selection_and_no_duplicate_video_in_settings(self):
        home=read("android-launcher/app/src/main/java/com/gow3/android/feature/home/HomeScreen.kt")
        popups=read("android-launcher/app/src/main/java/com/gow3/android/feature/home/HomePopups.kt")
        settings=read("android-launcher/app/src/main/java/com/gow3/android/feature/settings/GeneralSettingsScreen.kt")
        for label in ("FPS e VSync", "Vídeo e resolução", "Mods", "Cheats"):
            self.assertIn(label,home)
        self.assertIn("Dialog(onDismissRequest = onDismiss)",popups)
        self.assertIn("render_resolution",popups)
        self.assertIn("auto_qte",popups)
        self.assertNotIn("LaunchParameters(",home)
        self.assertNotIn("GpuDriverCard()",home)
        self.assertIn("GpuDriverCard()",settings)
        self.assertNotIn("Vídeo e resolução",settings)
        self.assertNotIn("FPS e VSync",settings)

    def test_mod_zip_order_and_runtime_game_view(self):
        mods=read("scripts/mods.py")
        sh=read("tools/android/bionic/run-bionic.sh")
        popup=read("android-launcher/app/src/main/java/com/gow3/android/feature/home/HomePopups.kt")
        self.assertIn("def unpack_zips(",mods)
        self.assertIn("def mod_info(",mods)
        self.assertIn("def conflicts(",mods)
        self.assertIn("def build_overlay(",mods)
        self.assertIn("--mods-dir",sh)
        self.assertIn('game=$mods_view',sh)
        self.assertIn("mods.json",popup)
        self.assertIn("JSONArray(order)",popup)
        self.assertIn("OpenDocument()",popup)

    def test_fex_cheats_and_upstream_qte_are_gate_by_signatures(self):
        probe=read("src/probe.c")
        self.assertIn("install_cheats_fex(",probe)
        self.assertLess(probe.index("#endif /* GUEST_CPU_NATIVE - x86 raw E9 hooks */"),
                        probe.index("static void install_cheats_fex("))
        self.assertIn("/* On AArch64, FEX hooks must compile independently",probe)
        self.assertIn("guest_cpu_hook(address, hook->length, gow3_fex_cheat_callback)",probe)
        self.assertIn("gow3_cheat_signature_match(",probe)
        self.assertIn("install_auto_qte_fex(",probe)
        self.assertIn("gow3_signature_find(image, size, signatures[i])",probe)
        self.assertIn("guest_cpu_hook(address, lengths[i], gow3_fex_qte_callback)",probe)
        self.assertIn("gow3_qte_status(fex_qte_count != 0)",probe)
        self.assertIn("auto_qte", read("gpu/shim/gow3_settings.cpp"))

if __name__ == "__main__":
    unittest.main()
