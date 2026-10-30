"""Guards for the GoW3-only mobile gamepad and fullscreen behavior."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"android-launcher/app/src/main"
JAVA=SRC/"java/ro/cobrabm/fexdroid"
COMPOSE=SRC/"java/com/gow3/android"
def load(path): return path.read_text(encoding="utf-8")

class Gow3MobileFullscreen(unittest.TestCase):
    def test_gsr2_is_selected_only_in_video_popup(self):
        home=load(COMPOSE/"feature/home/HomeScreen.kt")
        popup=load(COMPOSE/"feature/home/HomePopups.kt")
        self.assertNotIn('home_gsr2_summary_fmt',home)
        self.assertIn('HomePopupKind.VIDEO',home)
        self.assertIn('if (gsr2) "gsr2" else "off"',popup)
        self.assertIn('popup_gsr2_spatial_notice',popup)

    def test_fullscreen_is_one_persistent_ini_key(self):
        popup=load(COMPOSE/"feature/home/HomePopups.kt")
        general=load(COMPOSE/"feature/settings/GeneralSettingsScreen.kt")
        game=load(JAVA/"GameActivity.java")
        self.assertIn('"android_fullscreen" to (if (fullscreen) "1" else "0")',popup)
        self.assertIn('Gow3Ini.write(iniFile, mapOf("android_fullscreen" to value))',general)
        self.assertIn('boolean fullscreen="1".equals(setting("android_fullscreen"))',game)
        self.assertIn('Gow3Present.start(holder,BASE+"/present.sock","1".equals(setting("android_fullscreen")))',game)
        self.assertIn('c.hide(WindowInsets.Type.systemBars())',game)
        self.assertIn('getWindow().setDecorFitsSystemWindows(false)',game)
        self.assertIn('screen.requestApplyInsets()',game)
        self.assertIn('Gow3Present.updateFullscreen(fullscreen)',game)
        bridge=load(JAVA/"Gow3Present.java")
        native=load(ROOT/"tools/android/bionic/present/gow3present.c")
        self.assertIn('public static synchronized void updateFullscreen(boolean enabled)',bridge)
        self.assertIn('nativeSetFullscreen(enabled)',bridge)
        self.assertIn('_Atomic int fullscreen;',native)
        self.assertIn('atomic_load(&S.fullscreen)',native)
        self.assertIn('atomic_store(&S.fullscreen, enabled != 0)',native)

    def test_mobile_captions_are_only_gamepad_button_ids(self):
        overlay=load(JAVA/"TouchControllerOverlay.java")
        rendered=re.findall(r'gowAction\(c,"([^"]+)","([^"]*)",(\d+)\)',overlay)
        self.assertEqual(dict((name,label) for name,label,_ in rendered),{
            'l2':'L2','l1':'L1','r1':'R1','r2':'R2',
            'options':'','touchpad':'',
            'triangle':'△','square':'□','circle':'○','cross':'×',
            'rage':'L3 + R3','weapons':''
        })
        self.assertNotIn('faceCaption(',overlay)
        self.assertIn('preferences.getBoolean("overlay_button_labels",true)',overlay)

    def test_gow3_movement_and_evade_are_separate_touch_zones(self):
        overlay=load(JAVA/"TouchControllerOverlay.java")
        self.assertIn('return layoutCenter(name)',overlay)
        self.assertNotIn('moveOrigin=new PointF',overlay)
        self.assertIn('drawDodge(c)',overlay)
        self.assertIn('dodgeOrigin=new PointF(x,y)',overlay)
        self.assertIn('private boolean weaponsOpen',overlay)
        self.assertIn('controls.remove(id)',overlay)
        self.assertIn('gow3_mobile_v218_',overlay)
        self.assertIn('key("size",dragged)',overlay)

    def test_mobile_default_buttons_clear_screen_bars_and_preserve_combos(self):
        overlay=load(JAVA/"TouchControllerOverlay.java")
        match=re.search(r'private static final float\[\]\[\] DEFAULT=\{(.*?)\};',overlay,re.S)
        self.assertIsNotNone(match)
        points=[(int(a),int(b)) for a,b in re.findall(r'\{(\d+),(\d+)\}',match.group(1))]
        self.assertEqual(len(points),18)
        self.assertGreaterEqual(min(y for x,y in points),80)
        self.assertLessEqual(max(y for x,y in points),520)
        # L3 and R3 are never hidden: both are needed for Rage.
        self.assertIn('pressed.add("l3"); pressed.add("r3")',overlay)
        self.assertIn('gowAction(c,"rage","L3 + R3"',overlay)

    def test_panvk_notice_and_mali_driver_gate(self):
        ui=load(COMPOSE/"feature/home/GpuDriverCard.kt")
        manager=load(JAVA/"GpuDriverManager.java")
        self.assertIn('R.string.gpu_driver_mali_notice',ui)
        self.assertIn('GpuDriverManager.maliCandidate()',ui)
        self.assertIn('android.os.Build.VERSION.SDK_INT >= 35',ui)
        self.assertIn('supportedCsfMali',manager)
        en=load(SRC/"res/values/strings.xml")
        pt=load(SRC/"res/values-pt-rBR/strings.xml")
        self.assertIn('name="gpu_driver_mali_notice"',en)
        self.assertIn('name="gpu_driver_mali_notice"',pt)

if __name__=="__main__":
    unittest.main()
