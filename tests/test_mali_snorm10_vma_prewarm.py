"""Mali packed SNORM10 fallback and VMA cold-image regression guards.

Math tests cover all 1024 signed RGB codes (and four signed-alpha codes).
They intentionally do NOT treat UNORM or SINT as a normalized substitute.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def source(p):
    return (ROOT / p).read_text()

IMAGE = source("gpu/shadps4/video_core/texture_cache/image.cpp")
VIEWS = source("gpu/shadps4/video_core/texture_cache/image_view.cpp")
RUNTIME = source("gpu/shadps4/video_core/renderer_vulkan/vk_runtime.cpp")
INSTANCE = source("gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp")
SHADER = source("gpu/shadps4/video_core/host_shaders/snorm2101010.comp")


def host_code(value, max_code):
    if value <= -max_code - 1:
        return -32768
    value = min(max(value, -max_code), max_code)
    return (value * 32767 + (max_code // 2 if value >= 0 else -(max_code // 2))) // max_code if value >= 0 else -(((-value) * 32767 + max_code // 2) // max_code)


def guest_code(value, max_code):
    if value <= -32768:
        return -max_code - 1
    value = min(max(value, -32767), 32767)
    if value >= 0:
        return (value * max_code + 16383) // 32767
    return -(((-value) * max_code + 16383) // 32767)


class MaliSignedFormatTests(unittest.TestCase):
    def test_all_signed_rgb10_codes_survive_gpu_roundtrip(self):
        for n in range(-512, 512):
            self.assertEqual(n, guest_code(host_code(n, 511), 511), n)

    def test_all_signed_alpha2_codes_survive_gpu_roundtrip(self):
        for n in range(-2, 2):
            self.assertEqual(n, guest_code(host_code(n, 1), 1), n)

    def test_no_raw_unorm_reinterpretation_or_untested_driver_claim(self):
        self.assertIn("vk::Format::eA2B10G10R10SnormPack32", IMAGE)
        self.assertIn("vk::Format::eR16G16B16A16Snorm", IMAGE)
        self.assertIn("ProbeImageFormat(instance, alternate_info)", IMAGE)
        self.assertIn("image.transcoded_snorm2101010", VIEWS)
        self.assertIn("SNORM2101010_COMP", RUNTIME)
        cmake=(ROOT/"gpu/CMakeLists.txt").read_text()
        self.assertIn("add_host_shader(snorm2101010.comp snorm2101010_comp)", cmake)
        graphics=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_graphics_pipeline.cpp").read_text()
        self.assertIn('format == vk::Format::eA2B10G10R10SnormPack32', graphics)
        self.assertIn('color_format = vk::Format::eR16G16B16A16Snorm;', graphics)
        self.assertIn('GOW3_MALI_SNORM10_FALLBACK', graphics)
        self.assertIn("cmdbuf.copyImageToBuffer", RUNTIME)
        self.assertIn("vk::ImageLayout::eTransferDstOptimal, image_copy", RUNTIME)
        self.assertIn("vk::PipelineStageFlagBits2::eComputeShader", RUNTIME)
        self.assertIn("scale_to_16", SHADER)
        self.assertIn("scale_from_16", SHADER)
        self.assertIn("layout(local_size_x = 8, local_size_y = 8)", SHADER)
        self.assertIn("uvec2 texel = gl_GlobalInvocationID.xy;", SHADER)
        self.assertIn("(width + 7u) / 8u > limits.maxComputeWorkGroupCount[0]", RUNTIME)
        self.assertIn("(height + 7u) / 8u > limits.maxComputeWorkGroupCount[1]", RUNTIME)
        self.assertIn("cb.dispatch((params.width + 7u) / 8u,", RUNTIME)
        self.assertNotIn("eA2B10G10R10UnormPack32", IMAGE[IMAGE.index("// Mali G720 does not expose"):IMAGE.index("// Mali-only *host* BC1")])

    def test_prewarm_two_measured_cold_descriptions_only(self):
        prewarm = IMAGE[IMAGE.index("void PrewarmMaliImagePool("):IMAGE.index("void UniqueImage::Destroy()")]
        self.assertIn(".extent = {2048, 2048, 1}", prewarm)
        self.assertIn("rgba.extent = {4096, 248, 1}", prewarm)
        self.assertIn("etc2_square1024.extent = vk::Extent3D{1024, 1024, 1}",prewarm)
        self.assertIn("etc2_square1024.mipLevels = 10",prewarm)
        create=IMAGE.split("void UniqueImage::Create(",1)[1].split("Image::Image(",1)[0]
        self.assertIn("result == VK_ERROR_OUT_OF_DEVICE_MEMORY",create)
        self.assertIn("FlushMaliBcImagePool(allocator);",create)
        self.assertIn("GOW3_MALI_IMAGE_OOM_RETRY",create)
        self.assertIn("GOW3_MALI_VMA_PREWARM", prewarm)
        self.assertIn("VMA_ALLOCATION_CREATE_WITHIN_BUDGET_BIT", prewarm)
        self.assertIn("BcPoolHasBudget(allocator)", prewarm)
        self.assertIn("ReturnBcImage(allocator, ci", prewarm)
        self.assertIn('properties.vendorID == 0x13B5', INSTANCE)
        self.assertIn("VideoCore::PrewarmMaliImagePool(allocator", INSTANCE)


if __name__ == "__main__":
    unittest.main()
