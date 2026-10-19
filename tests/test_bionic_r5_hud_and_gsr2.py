"""Bionic R5: nine-position HUD, and verified CUSA01623 720p GSR2 source pipeline."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def source(path): return (ROOT/path).read_text(encoding="utf-8")

class R5(unittest.TestCase):
    def test_hud_has_only_requested_anchor_controls(self):
        controls=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/HudControls.java")
        self.assertIn('String[] verticalLabels = {"Top", "Center", "Bottom"}',controls)
        self.assertIn('{"Left", "Center", "Right"}',controls)
        self.assertNotIn("SeekBar",controls)
        self.assertIn("HudConfig.VERTICAL",controls)
        native=source("gpu/shim/gow3_overlay.cpp")
        for title in ('"Left"', '"Right"', '"Top"', '"Bottom"',
                      '"Center##horizontal"', '"Center##vertical"'):
            self.assertIn(title,native)
        self.assertNotIn('SliderRow("Horizontal shift"',native)
        self.assertNotIn('SliderRow("Move down"',native)
        view=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/PerfHudOverlay.java")
        self.assertIn("vertical == 0 ? marginPx : vertical == 1",view)
        self.assertIn("vertical = cfg.vertical;",view)
        settings=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/SettingsDialog.java")
        self.assertIn("!key.equals(HudConfig.VERTICAL)",settings)

    def test_shared_native_config_and_position(self):
        cpp=source("gpu/shim/gow3_settings.cpp")
        for text in ('key == "overlay_anchor_y"', 'overlay_anchor_y=%d',
                     'v.overlay_anchor_y.load()'):
            self.assertIn(text,cpp)
        header=source("gpu/shim/gow3_settings.h")
        self.assertIn("overlay_anchor_y{0}",header)
        java=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/HudConfig.java")
        self.assertIn('VERTICAL = "overlay_anchor_y"',java)
        self.assertIn("number(m.get(VERTICAL), 0)",java)

    def test_real_720p_input_and_forward_scene(self):
        launch=source("scripts/launch_env.py")
        for token in ("GOW3_PATCH_INPUT_RES", "'1280x720'", "'CUSA01623'",
                      "CUSA01715_0102_ANDROID_SHA", "Resolution Patch - 720p"):
            self.assertIn(token,launch)
        raster=source("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        for token in ("gsr2_forward", "std::popcount(key.mrt_mask & 0x7f) <= 2",
                      "scene_targets->EligibleScene(primary)", "scene_started = true"):
            self.assertIn(token,raster)
        camera=source("gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp")
        self.assertIn("gow3_android_gsr2",camera)
        upscale=source("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn("const VideoCore::ImageId scene = color;",upscale)
        self.assertIn("if (ui_phase && ++successful <= 3)",upscale)

if __name__ == "__main__": unittest.main()
