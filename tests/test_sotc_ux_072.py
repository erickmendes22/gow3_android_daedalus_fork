#!/usr/bin/env python3
"""Source regression gates for SotC 0.1.72 CUSA08034 and bundled GameHub."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
def read(path): return (ROOT / path).read_text()

class Sotc072(unittest.TestCase):
    def test_exact_title_and_eboot_gate(self):
        patch = read("ports/sotc/android/bachata_perf.py")
        self.assertIn('"CUSA08809", "CUSA08034"', patch)
        self.assertIn("21982727c6f97fd415b3af5e99c5e071619c4dcc2248787a701a31a45ab0a4e0", patch)
        self.assertIn("digest != EBOOT_SHA256", patch)
        self.assertIn("_verify_calls(elf, ph, requested)", patch)
        prepare = read("ports/sotc/android/prepare_game.py")
        self.assertIn("'CUSA08034':'US 1.00'", prepare)

    def test_single_exact_bundled_turnip(self):
        driver = read("ports/sotc/android/repack_sotc_072.py")
        self.assertIn("embed_verified_turnip(stage, driver_zip)", driver)
        self.assertIn("gamehub_dd_turnip_bundled\"] = True", driver)
        self.assertIn('"bundled": True', driver)
        self.assertIn("gen8", driver)
        self.assertIn("adreno7xx", driver)
        self.assertIn("LIB_SHA256", driver)
        launcher = read("ports/sotc/android/run-sotc-bionic.sh")
        self.assertIn('driver=${GOW3_BIONIC_DRIVER:-gamehub-dd}', launcher)
        self.assertIn('[ "$driver" = gamehub-dd ]', launcher)
        self.assertNotIn("driver=gen8", launcher)
        self.assertNotIn("driver=system", launcher)
        self.assertNotIn("gen8|adreno7xx|gamehub-dd|system", launcher)
        card = read("android-launcher/app/src/main/java/com/gow3/android/feature/home/GpuDriverCard.kt")
        self.assertIn("if (!isSotc) Row(", card)
        self.assertIn("if (!isSotc) DropdownMenu", card)
        manager = read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java")
        self.assertIn('SotcPaths.isSotc(context) ? "gamehub-dd"', manager)
        self.assertIn("GAMEHUB_DD_ELF_SHA256.equals(sha256(bundled))", manager)

    def test_install_in_new_folder_and_ui_without_update(self):
        screen = read("android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt")
        self.assertNotIn('SotcAction(if(pt) "Atualização"', screen)
        self.assertNotIn('SotcAction(if(pt) "PKG update"', screen)
        self.assertIn('SotcAction(if(pt) "Instalar PKG"', screen)
        installer = read("android-launcher/app/src/main/java/com/gow3/android/data/PkgInstallManager.kt")
        self.assertIn("createSotcSubfolder = !update && SotcPaths.isSotc", installer)
        self.assertIn('"Shadow of the Colossus" else "Shadow of the Colossus ($index)"', installer)
        self.assertIn("createdSotcSubfolder", installer)
        self.assertIn("dest.deleteRecursively()", installer)

    def test_package_identity(self):
        gradle = read("android-launcher/app/build.gradle.kts")
        self.assertIn("versionCode = 10072", gradle)
        self.assertIn('versionName = "0.1.72-cusa08034-gamehub"', gradle)
        self.assertIn('manifestPlaceholders["appLabel"] = "Shadow of the Colossus"', gradle)
        packer = read("ports/sotc/android/repack_sotc_072.py")
        self.assertIn('"sotcport/scripts/bachata_perf.py":', packer)
        self.assertIn('"sotcport/scripts/sotc_prepare_game.py":', packer)
        self.assertIn("SOTC", read("ports/sotc/android/run-sotc-bionic.sh"))

if __name__ == "__main__":
    unittest.main()
