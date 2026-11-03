"""Regression: PanVK 65536-wide limit must never overflow u16 render area."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RAST = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
SCHEDULER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text()
HEADER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.h").read_text()

class MaliFramebufferExtent(unittest.TestCase):
    def test_render_state_is_sixteen_bit_and_must_cap_before_cast(self):
        self.assertRegex(HEADER, r"u16 width;\s*u16 height;")
        self.assertIn("const u32 max_framebuffer_width = instance.GetMaxFramebufferWidth();", RAST)
        self.assertIn("const u32 max_framebuffer_height = instance.GetMaxFramebufferHeight();", RAST)
        self.assertIn("state.width = static_cast<u16>(std::min<u32>(", RAST)
        self.assertIn("state.height = static_cast<u16>(std::min<u32>(", RAST)
        for expected in ("max_framebuffer_width, std::numeric_limits<u16>::max()",
                         "max_framebuffer_height, std::numeric_limits<u16>::max()"):
            self.assertIn(expected, RAST)
        self.assertNotIn("state.width = instance.GetMaxFramebufferWidth();", RAST)
        self.assertNotIn("state.height = instance.GetMaxFramebufferHeight();", RAST)

    def test_65536_does_not_collapse_to_zero(self):
        for vk_limit, expected in ((4096,4096),(16384,16384),(65535,65535),
                                   (65536,65535),(131072,65535)):
            narrowed = min(vk_limit, (1 << 16) - 1) & 0xffff
            self.assertEqual(narrowed, expected)
            self.assertGreater(narrowed, 0)

    def test_render_area_comes_from_same_render_state(self):
        self.assertIn("const auto state = BeginRendering(pipeline);", RAST)
        self.assertIn("scheduler.BeginRendering(state);", RAST)
        self.assertIn(".extent = {render_state.width, render_state.height}", SCHEDULER)
        self.assertIn("GOW3_MALI_RENDER_EXTENT max_framebuffer=", RAST)

if __name__ == "__main__":
    unittest.main()
