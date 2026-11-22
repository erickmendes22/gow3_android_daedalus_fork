#!/usr/bin/env python3
"""Regression gates for SotC 0.1.70: driver correctness, native 30 FPS and UI."""
from pathlib import Path
import re,unittest
ROOT=Path(__file__).resolve().parents[1]
def source(path):return (ROOT/path).read_text()

class SotcUx070(unittest.TestCase):
    def test_version_and_hash_verified_driver_only(self):
        gradle=source("android-launcher/app/build.gradle.kts")
        self.assertIn("versionCode = 10070",gradle)
        self.assertIn('"0.1.70-gamehub-ui"',gradle)
        manager=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java")
        self.assertIn('SotcPaths.isSotc(context) ? "gamehub-dd"',manager)
        self.assertIn('SotcPaths.isSotc(context) && !"gamehub-dd".equals(value)',manager)
        self.assertIn("GAMEHUB_DD_ELF_SHA256.equals(sha256(result.library))",manager)
        self.assertIn('SotcPaths.isSotc(context) && !hasGameHubDD(context)',manager)
        card=source("android-launcher/app/src/main/java/com/gow3/android/feature/home/GpuDriverCard.kt")
        self.assertIn('"gamehub-dd" to "Turnip GameHub DD 26.3',card)
        self.assertIn('if (!isSotc) DropdownMenu',card)
        runtime=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/RuntimeInstaller.java")
        sotc=runtime.split('if (path(root,"sotcport/run-sotc-bionic.sh").isFile()) {',1)[1].split('return;',1)[0]
        self.assertNotIn('"sotcport/arm64/drivers/gen8/libvulkan_freedreno.so"',sotc)
        repack=source("ports/sotc/android/repack_sotc_070.py")
        self.assertIn('sotcport/arm64/drivers/gen8',repack)
        self.assertIn('sotcport/arm64/drivers/adreno7xx',repack)
        self.assertIn('gamehub-dd-26.3',repack)

    def test_hud_exactly_reuses_tlou_widget_not_fake_target(self):
        hud=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/HudPresentation.java")
        self.assertIn("0xff76ff03",hud)
        self.assertIn('String.format(Locale.ROOT,"FPS %.0f"',hud)
        java=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java")
        self.assertIn('HudPresentation.style(sotcFpsHud,',java)
        self.assertIn('HudPresentation.text("compact",fps',java)
        self.assertIn('sotcFpsMeter.sample(frames,now)',java)
        self.assertNotIn('game 60 FPS',java)
        self.assertIn('String modes="";',java)
        aot=source("android-launcher/app/src/main/java/com/gow3/android/data/SotcAotBuildManager.kt")
        self.assertIn('mutableListOf<String>()',aot)
        self.assertNotIn('mutableListOf("fps60game")',aot)

    def test_game_and_launcher_language_separate(self):
        language=source("android-launcher/app/src/main/java/com/gow3/android/data/LanguageManager.kt")
        self.assertIn('SotcPaths.prefsName(context)',language)
        self.assertIn('Locale.getDefault()',language)
        sfo=source("android-launcher/app/src/main/java/com/gow3/android/data/GameSfo.kt")
        self.assertIn('fun sotcLanguage(',sfo)
        java=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java")
        self.assertIn('GameSfo.sotcLanguage(',java)
        self.assertIn('"sotc_game_language","system"',java)
        screen=source("android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt")
        self.assertIn('sotc_game_language',screen)
        self.assertIn('onChangeLanguage)',screen)
        self.assertNotIn('NO FEX',screen)
        self.assertNotIn('sem FEX',screen)

    def test_real_game_art_and_autoplay(self):
        screen=source("android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt")
        for asset in ('pic1.png','pic0.png','icon0.png'):
            self.assertIn(asset,screen)
        self.assertIn('SotcGameArtwork(gameDir)',screen)
        self.assertIn('"sotc_auto_start"',screen)
        launcher=source("android-launcher/app/src/main/java/com/gow3/android/MainActivity.kt")
        self.assertIn('autoStartAttempted',launcher)
        self.assertIn('sotcAotBuilder.ensureReadyThen',launcher)

    def test_no_spontaneous_relaunch_and_exit_routes(self):
        java=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java")
        self.assertIn('!gameLaunchedOnce',java)
        self.assertIn('gameLaunchedOnce=true;',java)
        self.assertIn('"Return to launcher"',java)
        self.assertIn('"Exit application"',java)
        self.assertIn('finishAffinity()',java)
        controls=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/TouchControllerOverlay.java")
        self.assertIn('preventOverlap()',controls)
        self.assertIn('for(int pass=0;pass<48;pass++)',controls)
        self.assertIn('editor.putFloat("overlay_x_"+name,p.x)',controls)

if __name__ == "__main__":unittest.main()
