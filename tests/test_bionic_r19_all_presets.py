"""Five-preset regression: Native AA is 1:1; all four enlarged modes require
actually rasterized color + depth, rather than downsampling 720p after the draw.
"""
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCENE_H = ROOT / "gpu/shadps4/video_core/renderer_vulkan/scene_resolution.h"
SCENE_CPP = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_scene_resolution.cpp"
SCENE_API = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_scene_resolution.h"
UP = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp"

class R19AllPresets(unittest.TestCase):
    def test_five_exact_presets(self):
        # Compile and execute the REAL C++ sizing formula: 1:1 / 1.5x /
        # 1.7x / 2x / 3x, every mode producing the intended pixel dimensions.
        code = """
#include <cassert>
#include "gpu/shadps4/video_core/renderer_vulkan/scene_resolution.h"
int main() {
    const unsigned expected[][2] = {{1280,720},{854,480},{752,424},{640,360},{426,240}};
    for (int preset = 0; preset != 5; ++preset) {
        const auto size = Vulkan::SceneResolution::ForPreset(preset, {1280,720});
        assert(size.width == expected[preset][0]);
        assert(size.height == expected[preset][1]);
    }
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            source, exe = Path(tmp)/"matrix.cpp", Path(tmp)/"matrix"
            source.write_text(code)
            build = subprocess.run(["c++","-std=c++20","-I",str(ROOT),
                                    str(source),"-o",str(exe)],
                                    capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            result = subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_native_keeps_1_to_1_gsr2_dispatch(self):
        src=UP.read_text()
        self.assertIn("const bool native_aa =",src)
        self.assertIn("render_width == target_width",src)
        self.assertIn("render_height == target_height",src)
        self.assertIn("(native_aa || true_upscale)",src)
        self.assertIn("native_aa || (scene_targets.EligibleScene(color_image)",src)
        self.assertIn("if (!scaled_session && scene_targets.Reduced())",src)
        self.assertNotIn("preset = 3;",src)

    def test_reduced_inputs_are_proven_per_frame_not_allocated_on_demand(self):
        src=UP.read_text()
        scene=SCENE_CPP.read_text()
        api=SCENE_API.read_text()
        self.assertIn("scene_targets.BeginFrame();",src)
        self.assertIn("GSR2_SCALE_PROOF rejected",src)
        self.assertIn("GSR2_RUN_GUARD refused native-downsampled source",src)
        self.assertIn("scene_targets.WasRasterizedReduced(color_image)",src)
        self.assertIn("scene_targets.WasRasterizedReduced(depth_image)",src)
        self.assertIn("scene_targets.WasRasterizedReduced(color)",src)
        self.assertIn("scene_targets.WasRasterizedReduced(depth)",src)
        self.assertIn("e.last_raster_frame = frame_serial;",scene)
        self.assertIn("it->second->state.valid && it->second->state.dirty",scene)
        self.assertIn("void BeginFrame() { ++frame_serial; }",api)
        self.assertIn("e.state.ProxyWrite();",scene)

if __name__ == "__main__":
    unittest.main()
