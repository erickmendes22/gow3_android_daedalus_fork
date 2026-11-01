"""Render correctness protection for Mali depth format promotion and effects.
This is a preflight source contract; native compile and hardware still required.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_runtime.cpp").read_text()
LAUNCH = (ROOT / "scripts/launch_env.py").read_text()


class MaliPhysicalDepthBridge(unittest.TestCase):
    def test_copy_size_uses_real_allocated_gpu_image_format(self):
        self.assertIn("src->backing->image.image_ci.format", RUNTIME)
        self.assertIn("BufferImageCopySize(buffer_copy, physical_source_format)", RUNTIME)
        self.assertNotIn("BufferImageCopySize(buffer_copy, src->info.pixel_format)", RUNTIME)
        self.assertIn("PanVK image bridge: guest format", RUNTIME)

    def test_mali_specific_restoration_of_native_render_passes(self):
        self.assertIn("libvulkan_panfrost.so", LAUNCH)
        self.assertIn("GOW3_MALI_SAFE_MODE", LAUNCH)
        for patch in ("Disable Dynamic Shadows", "Disable SSAO",
                      "Disable Motion Blur", "Disable Depth of Field",
                      "Disable Bloom", "Disable Soft Particles"):
            self.assertIn(patch, LAUNCH)
        self.assertIn("native-render-passes-restored", LAUNCH)
        self.assertIn("GOW3_MALI_EFFECT_PATCHES_FILTERED", LAUNCH)
        self.assertIn("enabled-mali-render-compat", LAUNCH)


if __name__ == "__main__":
    unittest.main()
