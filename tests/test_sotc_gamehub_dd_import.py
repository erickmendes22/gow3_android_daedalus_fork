#!/usr/bin/env python3
"""Exact user-supplied GameHub DD Turnip integrates through the real Android HAL."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
GPU=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java").read_text()
CARD=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/feature/home/GpuDriverCard.kt").read_text()
RUN=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
BUNDLE=(ROOT/"ports/sotc/android/vendor_turnip.py").read_text()
PACKAGE=(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text()

ZIP_SHA="8255659cc205110e0fa89f2d364292b86fe563a2cedafbc41915bead5a611ecb"
SO_SHA="4f242a453496ab27fc29be950d632edbae494dcc0c9b7d56c37c7ebdffe42df9"

class GameHubDDImport(unittest.TestCase):
    def test_exact_bin_can_be_selected_when_imported_or_bundled(self):
        for sha in (ZIP_SHA,SO_SHA):
            self.assertIn(sha,GPU)
            self.assertIn(sha,BUNDLE)
        self.assertIn("verifiedImportedGameHubDD(context)",GPU)
        self.assertIn("hasBundledGameHubDD(context) || verifiedImportedGameHubDD(context)!=null",GPU)
        self.assertIn("GAMEHUB_DD_ARCHIVE_SHA256.equals(result.id)",GPU)
        self.assertIn('environment.put("GOW3_CUSTOM_VULKAN_DRIVER",driver.library.getAbsolutePath())',GPU)
        self.assertIn('environment.put("GOW3_BIONIC_DRIVER","custom")',GPU)
        self.assertIn('"gamehub-dd" to "Turnip GameHub 26.3', CARD)
        self.assertIn("GpuDriverManager.hasGameHubDD(context)",CARD)

    def test_not_silently_replacing_system_or_other_drivers(self):
        self.assertIn("if (!hasGameHubDD(context)) throw new IOException",GPU)
        self.assertIn("gen8|adreno7xx|gamehub-dd|system|custom",RUN)
        self.assertIn("driver=gamehub-dd",RUN)
        self.assertIn('GOW3_CUSTOM_VULKAN_DRIVER',RUN)
        self.assertIn("gamehub_dd_turnip_bundled=driver_included",PACKAGE)
        self.assertIn("if not archive.is_file():",BUNDLE)

if __name__=="__main__":
    unittest.main()
