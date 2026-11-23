#!/usr/bin/env python3
"""0.1.73 regression: automatically install the SHA-verified GameHub on launcher entry."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def src(path): return (ROOT/path).read_text()
class BundledTurnipStartup(unittest.TestCase):
    def test_launcher_installs_runtime_before_negative_driver_result(self):
        screen=src('android-launcher/app/src/main/java/com/gow3/android/feature/home/GpuDriverCard.kt')
        self.assertIn('LaunchedEffect(isSotc)',screen)
        self.assertIn('RuntimeInstaller.ensure(context, context.filesDir)',screen)
        self.assertIn('withContext(Dispatchers.IO)',screen)
        self.assertIn('GpuDriverManager.hasBundledGameHubDD(context)',screen)
        self.assertIn('preparingRuntime ->',screen)
        self.assertIn('runtimeError != null ->',screen)
        self.assertNotIn('Reinstale o APK completo.',screen)
    def test_runtime_mandates_exact_driver_before_promotion(self):
        java=src('android-launcher/app/src/main/java/ro/cobrabm/fexdroid/RuntimeInstaller.java')
        self.assertIn('"sotcport/arm64/drivers/gamehub-dd/libvulkan_freedreno.so"',java)
        self.assertIn('validateRuntime(stage)',java)
        self.assertIn('preserveUserData(files, stage)',java)
        self.assertIn('promote(files, stage, expected)',java)
        manager=src('android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java')
        self.assertIn('GAMEHUB_DD_ELF_SHA256.equals(sha256(bundled))',manager)
        self.assertIn('return SotcPaths.isSotc(context) ? "gamehub-dd"',manager)
    def test_version_and_previous_invariants(self):
        gradle=src('android-launcher/app/build.gradle.kts')
        self.assertIn('versionCode = 10073',gradle)
        self.assertIn('versionName = "0.1.73-gamehub-runtime-ready"',gradle)
        self.assertIn('applicationId = "com.sotc.android.daedalus"',gradle)
        source=src('ports/sotc/android/repack_sotc_073.py')
        self.assertIn('0.1.73-gamehub-runtime-ready',source)
        self.assertIn('embed_verified_turnip(stage, driver_zip)',source)
        self.assertIn('LIB_SHA256',source)
        self.assertIn('"bundled": True',source)
        launcher=src('ports/sotc/android/run-sotc-bionic.sh')
        self.assertIn('driver=${GOW3_BIONIC_DRIVER:-gamehub-dd}',launcher)
        self.assertNotIn('driver=gen8',launcher)
        self.assertNotIn('driver=system',launcher)
        patch=src('ports/sotc/android/bachata_perf.py')
        self.assertIn('"CUSA08809", "CUSA08034"',patch)
        self.assertIn('digest != EBOOT_SHA256',patch)
if __name__=="__main__":unittest.main()
