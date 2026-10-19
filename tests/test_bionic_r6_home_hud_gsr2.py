"""R6 regressions: Compose home position options + GSR2 safe invalid-motion mode."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def src(p): return (ROOT/p).read_text(encoding="utf-8")
class R6(unittest.TestCase):
    def test_compose_home_has_separate_horizontal_and_vertical_dropdowns(self):
        kotlin=src("android-launcher/app/src/main/java/com/gow3/android/data/LaunchParams.kt")
        self.assertIn('key = "overlay_corner", labelRes = R.string.param_fps_horizontal',kotlin)
        self.assertIn('key = "overlay_anchor_y", labelRes = R.string.param_fps_vertical',kotlin)
        self.assertIn('LaunchOption("0", R.string.fps_left)',kotlin)
        self.assertIn('LaunchOption("4", R.string.fps_center)',kotlin)
        self.assertIn('LaunchOption("1", R.string.fps_right)',kotlin)
        self.assertIn('LaunchOption("0", R.string.fps_top)',kotlin)
        self.assertIn('LaunchOption("1", R.string.fps_middle)',kotlin)
        self.assertIn('LaunchOption("2", R.string.fps_bottom)',kotlin)
        self.assertNotIn('key = "overlay_corner", labelRes = R.string.param_fps_position',kotlin)
        for path in ("android-launcher/app/src/main/res/values/strings.xml",
                     "android-launcher/app/src/main/res/values-pt-rBR/strings.xml"):
            labels=src(path)
            for name in ("param_fps_horizontal","param_fps_vertical","fps_left",
                         "fps_center","fps_right","fps_top","fps_middle","fps_bottom"):
                self.assertIn(f'<string name="{name}">',labels)

    def test_gsr2_no_motion_never_accumulates_invalid_history(self):
        cpp=src("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn("const bool temporal_ready = camera_motion.Ready();",cpp)
        self.assertIn(".reset = reset || !temporal_ready,",cpp)
        self.assertIn(".camera_still = temporal_ready ? camera_motion.CameraStill() : true,",cpp)
        self.assertIn("running current-frame spatial reconstruction",cpp)
        self.assertIn("if (UseGsr2() && std::getenv(\"GOW3_ANDROID_PORT\") && preset > 3)",cpp)
        glsl=src("gpu/shadps4/video_core/host_shaders/gsr2_upscale.comp")
        self.assertIn("float(params.reset)",glsl)
        self.assertIn("mix(HistoryColor, Upsampledcw.xyz, alpha)",glsl)
        self.assertIn("float(params.reset)",glsl)

if __name__ == "__main__": unittest.main()
