"""R4 regressions: ONE Bionic FPS HUD, shared launcher/in-game controls, and
a real GSR2 display-boundary dispatch path (not a UI-only setting).
"""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding="utf-8")

class UnifiedHudR4Tests(unittest.TestCase):
    def test_old_native_hud_is_not_rendered_on_android(self):
        overlay=read("gpu/shim/gow3_overlay.cpp")
        self.assertIn('s.show_fps && !std::getenv("GOW3_ANDROID_PORT")',overlay)
        self.assertIn('!menu_open && !std::getenv("GOW3_ANDROID_PORT")',overlay)
        self.assertIn('Performance HUD (FPS / GPU / CPU)',overlay)

    def test_native_menu_controls_launcher_hud(self):
        native=read("gpu/shim/gow3_overlay.cpp")
        for label in ('"Horizontal position"', '"Vertical position"', '"Left"',
                      '"Center##horizontal"', '"Right"', '"Top"', '"Bottom"'):
            self.assertIn(label,native)
        settings=read("gpu/shim/gow3_settings.cpp")
        for field in ('overlay_offset_x','overlay_offset_y','overlay_corner','overlay_anchor_y'):
            self.assertIn('key == "'+field+'"',settings)
            self.assertIn(field+'=%d',settings)
        self.assertIn("Gow3Settings::ReloadHudFromDisk();",native)

    def test_android_has_one_animated_two_row_overlay(self):
        view=read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/PerfHudOverlay.java")
        self.assertIn("lineH * 2 + padPx * 3",view)
        self.assertIn("Math.max(first, second)",view)
        self.assertIn("if (!dragging) alignToAnchor()",view)
        self.assertIn("void setConfiguration(HudConfig cfg)",view)
        self.assertIn("HudConfig.update(",view)
        self.assertIn("vertical == cfg.vertical",view)
        self.assertNotIn('prefs.edit().putFloat("perf_hud_x"',view)

    def test_launcher_and_drawer_share_gow3_ini(self):
        activity=read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java")
        self.assertIn("HudConfig.migrateLegacy",activity)
        self.assertIn("HudConfig.load(new File(BASE",activity)
        self.assertIn("HudControls.show(this,new File(BASE",activity)
        graphics=read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/SettingsDialog.java")
        self.assertIn("new HudControls(activity, file, box",graphics)
        self.assertIn("changed.putAll(hud.values())",graphics)
        self.assertNotIn('toggle(box,"Show FPS"',graphics)
        cfg=read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/HudConfig.java")
        self.assertIn('static final String DX = "overlay_offset_x"',cfg)
        self.assertIn('static final String DY = "overlay_offset_y"',cfg)
        self.assertIn('static final String VERTICAL = "overlay_anchor_y"',cfg)
        controls=read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/HudControls.java")
        self.assertNotIn("SeekBar",controls)
        self.assertIn('String[] verticalLabels = {"Top", "Center", "Bottom"}',controls)

    def test_snapdragon_dispatch_reaches_scene_boundary(self):
        source=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn('if (UseGsr2() && !scaled_session && std::getenv("GOW3_ANDROID_PORT"))',source)
        self.assertIn("scene_targets.EligibleScene(color_image)",source)
        self.assertIn("scene_targets.EligibleScene(depth_image)",source)
        self.assertIn("RunScaled(); // After the completed scene",source)
        self.assertIn("GSR2: real Vulkan dispatch recorded",source)
        self.assertIn("GSR2: display boundary skipped",source)

if __name__=="__main__":
    unittest.main()
