#!/usr/bin/env python3
"""SotC 0.1.69 user interface and AOT verification regression checks."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

def get(path):
    return (ROOT / path).read_text()

class SotcUx069Tests(unittest.TestCase):
    def test_launch_requires_verified_aot(self):
        main=get("android-launcher/app/src/main/java/com/gow3/android/MainActivity.kt")
        self.assertIn("sotcAotBuilder.ensureReadyThen",main)
        manager=get("android-launcher/app/src/main/java/com/gow3/android/data/SotcAotBuildManager.kt")
        self.assertIn('if (execute("verify") == 0)',manager)
        self.assertIn('val code = execute("compile")',manager)
        self.assertIn("if (ready && onReady != null)",manager)
        self.assertIn('env["SOTC_SUN_CASCADES"]',manager) if False else None
        self.assertIn('"SOTC_SUN_CASCADES" to "5"',manager)
        self.assertIn('"SOTC_RENDER" to "1280x720"',manager)
        self.assertIn('mutableListOf("fps60game")',manager)

    def test_bash_verifier_and_patch_profile_reuse(self):
        sh=get("ports/sotc/android/run-sotc-bionic.sh")
        self.assertIn("game|compile|verify)",sh)
        self.assertIn('if [ "$sotc_mode" = verify ]; then',sh)
        self.assertIn('SOTC_AOT_VERIFIED: reused compiled patch profile',sh)
        self.assertIn("aot-profiles/previous-1",sh)
        self.assertIn('if [ "$sotc_mode" = compile ]; then',sh)
        self.assertIn('SOTC_AOT_READY:',sh)
        self.assertIn('sotc_aot_select.py',sh)

    def test_no_obsolete_experiment_in_user_patch_page(self):
        screen=get("android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt")
        section=screen.split('            1 -> {',1)[1].split('            else -> {',1)[0]
        for name in ("sotc_bachata_bloom","sotc_blur_suppression","sotc_bachata_ssr",
                     "sotc_bachata_fog","sotc_bachata_shadows","sotc_af16"):
            self.assertIn(name,section)
        for name in ("sotc_sun_cascades","sotc_perf_profile","sotc_trial039_dma_32m",
                     "sotc_adreno_wave32","sotc_taa_history"):
            self.assertNotIn('values["'+name+'"]',screen)
        self.assertNotIn('COMPILAR AOT NO CELULAR',screen)

    def test_working_renderer_profile_is_fixed_not_user_experiment(self):
        java=get("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java")
        for line in (
            'env.put("SOTC_RENDER","1280x720")',
            'env.put("BB_READBACKS","2")',
            'env.put("SOTC_RB_HOT","1")',
            'env.put("SOTC_TAA_OFF","1")',
            'env.put("SOTC_PERF_PROFILE","0")',
            'env.put("SOTC_SUN_CASCADES","5")',
        ):
            self.assertIn(line,java)

    def test_hud_and_controls(self):
        java=get("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java")
        self.assertIn('"FPS %.1f  |  %.1f ms"',java)
        self.assertIn('hudPrefs.edit().putFloat("sotc_hud_x"',java)
        self.assertIn("controllerOverlay.setCameraSensitivity",java)
        self.assertIn("controllerOverlay.setControlSize",java)
        overlay=get("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/TouchControllerOverlay.java")
        self.assertIn("controlScale()",overlay)
        self.assertIn('"controller_camera_sensitivity"',overlay)
        self.assertIn("SotcPaths.prefsName(context)",overlay)
        self.assertIn("if (name==null && !mouseEnabled)",overlay)

    def test_new_version(self):
        gradle=get("android-launcher/app/build.gradle.kts")
        self.assertIn("versionCode = 10069",gradle)
        self.assertIn("0.1.69-aot-ux",gradle)
        pkg=get("ports/sotc/android/package_sotc_runtime.py")
        self.assertIn("0.1.69-aot-ux",pkg)

if __name__ == "__main__":
    unittest.main()
