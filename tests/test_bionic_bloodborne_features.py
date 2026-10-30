"""Regression guards for the Bloodborne-derived native frame generation and GSR2 path."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding="utf-8")

class BionicBloodborneFeatureTests(unittest.TestCase):
    def test_framegen_mismatched_game_and_phone_display_is_supported(self):
        presenter = read("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
        self.assertIn("frame->width > 0 && frame->height > 0", presenter)
        self.assertNotIn("frame->width == expected_frame_width && frame->height == expected_frame_height &&",presenter)
        self.assertIn("PresentWithLsfg(frame)", presenter)

    def test_gsr2_runtime_is_preserved_but_in_game_controls_are_hidden(self):
        java = read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/SettingsDialog.java")
        graphics=java.split("    void show() {",1)[1].split(
            "    /** Saves the changed keys",1)[0]
        self.assertNotIn("Snapdragon Game Super Resolution",graphics)
        self.assertNotIn("GSR2 rendering preset",graphics)
        # The old in-game temporal preset menu stays hidden, but the
        # explicit 1:1 spatial filter may be toggled like any image option.
        self.assertIn('toggle(box,"GSR2 spatial filter (no temporal)"',graphics)
        self.assertIn('changed.put("upscaler",gsr2Spatial.isChecked()',graphics)
        self.assertNotIn('changed.put("preset"',graphics)
        settings=read("gpu/shim/gow3_settings.cpp")
        self.assertIn('if (key == "upscaler")',settings)
        self.assertIn('key == "preset"',settings)
        # The 5 reconstruction ratios remain in the renderer for future use.
        presets=read("gpu/shadps4/video_core/renderer_vulkan/scene_resolution.h")
        self.assertIn("scales{1.0, 1.5, 1.7, 2.0, 3.0}",presets)

    def test_bloodborne_framegen_settings_preserved_in_home(self):
        java = read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/FrameGenDialog.java")
        for text in ("multiplier=", "flow=", "performance=", "fp16=", "Engine active:"):
            self.assertIn(text, java)
        home = read("android-launcher/app/src/main/java/com/gow3/android/data/FrameGenStorage.kt")
        for key in ("framegen_flow", "framegen_performance", "framegen_fp16"):
            self.assertIn(key, home)

    def test_save_icon_fallback_is_valid_c11_not_cpp_if_initializer(self):
        runtime=read("src/runtime_savedata.c")
        self.assertNotIn('if (const char *game=getenv(', runtime)
        self.assertIn('const char *game=getenv("GOW3_GAME_DIR");', runtime)
        self.assertIn('if (game && *game)', runtime)

    def test_save_dialog_keeps_touch_navigation_but_not_shoulder_obscuration(self):
        overlay=read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/TouchControllerOverlay.java")
        runtime=read("src/runtime_services.c")
        self.assertIn('GOW3_SAVE_DIALOG_ACTIVE_FILE',runtime)
        self.assertIn('savedata_modal_visible(1)',runtime)
        self.assertIn('savedata_modal_visible(0)',runtime)
        for name in ('cross','circle','dpad'):
            self.assertIn('name.equals("'+name+'")',overlay)
        self.assertIn('if (!modal || editing)',overlay)

if __name__ == "__main__":
    unittest.main()
