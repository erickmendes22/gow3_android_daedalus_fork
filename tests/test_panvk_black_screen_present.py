"""Guards the Mali-specific sampled AHB video-out path against regressions."""
from pathlib import Path
import unittest

R = Path(__file__).resolve().parents[1]

def read(path):
    return (R / path).read_text()

class PanvkFinalCopy(unittest.TestCase):
    def test_shader_copy_is_real_draw(self):
        src = read("gpu/shadps4/video_core/renderer_vulkan/host_passes/pp_pass.cpp")
        self.assertIn("PostProcessingPass::RenderToSwapchain", src)
        self.assertIn("cmdbuf.beginRendering(rendering)", src)
        self.assertIn("cmdbuf.draw(3, 1, 0, 0)", src)
        self.assertIn(".loadOp = vk::AttachmentLoadOp::eLoad", src)
        self.assertIn("const Settings identity", src)
    def test_avoids_panvk_blit_and_preserves_standard_blit(self):
        src = read("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
        self.assertIn("const bool shader_present = force_shader || !blit_supported;", src)
        self.assertIn("pp_pass.RenderToSwapchain(cmdbuf", src)
        self.assertIn("cmdbuf.blitImage(frame->image", src)
        self.assertIn("vk::ImageLayout::eShaderReadOnlyOptimal", src)
        self.assertIn("vk::FormatFeatureFlagBits::eSampledImageFilterLinear", src)
        self.assertIn("VideoOut final copy:", src)
    def test_ahb_format_guards_for_shader_copy(self):
        src = read("gpu/shadps4/video_core/renderer_vulkan/vk_swapchain_ahb.cpp")
        self.assertIn("shader_fallback ? vk::FormatFeatureFlagBits::eTransferDst", src)
        self.assertIn("vk::FormatFeatureFlagBits::eColorAttachment", src)
    def test_only_panvk_gets_forced_shader_copy(self):
        src = read("tools/android/bionic/run-bionic.sh")
        mali=src.index("*/libvulkan_panfrost.so)")
        shader=src.index("export GOW3_PANVK_SHADER_PRESENT=1")
        end=src.index("esac",mali)
        self.assertTrue(mali < shader < end)
        self.assertIn('GOW3_MALI_SAFE_MODE', src)

if __name__ == '__main__':
    unittest.main()
