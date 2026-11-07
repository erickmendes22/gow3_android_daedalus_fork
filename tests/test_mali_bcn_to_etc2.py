"""PanVK BC1/BC3 -> ETC2: source-format, upload and hazard safety gates.

Full GLSL compile and ARM64 C++ compile are separately run by the native-only CI.
These tests are NOT FPS measurements and do not validate actual Mali output.
"""
from pathlib import Path
import random
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHADER = (ROOT / "gpu/shadps4/video_core/host_shaders/bcn_to_etc2.comp").read_text()
IMAGE = (ROOT / "gpu/shadps4/video_core/texture_cache/image.cpp").read_text()
VIEW = (ROOT / "gpu/shadps4/video_core/texture_cache/image_view.cpp").read_text()
RUNTIME = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_runtime.cpp").read_text()
RUN = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()
CMAKE = (ROOT / "gpu/CMakeLists.txt").read_text()


def bc3_selector_emulation(word0: int, word1: int, pixel: int) -> int:
    bit = 16 + 3 * pixel
    if bit >= 32:
        return (word1 >> (bit - 32)) & 7
    bits = word0 >> bit
    if bit > 29:
        bits |= word1 << (32 - bit)
    return bits & 7


def pack_eac_alpha_indices(selectors, base=137, multiplier=5):
    """Reimplements the GLSL 2x32-bit EAC MSB-first column-major packing."""
    hi = (base << 24) | (multiplier << 20)
    lo = 0
    for i in range(16):
        x, y = i // 4, i % 4
        sel = selectors[4 * y + x]
        bit = 45 - 3 * i
        if bit >= 32:
            hi |= sel << (bit - 32)
        elif bit >= 30:
            hi |= sel >> (32 - bit)
            lo |= sel << bit
        else:
            lo |= sel << bit
    return (hi & 0xffffffff).to_bytes(4, "big") + (lo & 0xffffffff).to_bytes(4, "big")


class TestMaliBcnToEtc2(unittest.TestCase):
    def test_etc2_alpha_is_big_endian_column_major(self):
        rnd = random.Random(480)
        for _ in range(200):
            selectors = [rnd.randrange(8) for _ in range(16)]
            payload = pack_eac_alpha_indices(selectors)
            self.assertEqual(payload[0], 137)
            self.assertEqual(payload[1], 0x50)  # multiplier=5, modifier table=0
            encoded = int.from_bytes(payload[2:8], "big")
            extracted = [((encoded >> (45 - 3 * i)) & 7)
                         for i in range(16)]
            expected = [selectors[4 * (i % 4) + (i // 4)]
                        for i in range(16)]
            self.assertEqual(extracted, expected)

    def test_bc3_alpha_selector_cross_word_boundary(self):
        rand = random.Random(173)
        for _ in range(200):
            selectors = [rand.randrange(8) for _ in range(16)]
            packed = sum(x << (16 + 3*i) for i, x in enumerate(selectors))
            word0, word1 = packed & 0xffffffff, (packed >> 32) & 0xffffffff
            self.assertEqual([bc3_selector_emulation(word0, word1, i) for i in range(16)],
                             selectors)

    def test_glsl_encoding_has_bc1_bc3_and_eac_alpha(self):
        self.assertIn('layout(local_size_x = 8, local_size_y = 8', SHADER)
        self.assertIn('pc.bc_words == 4u', SHADER)
        self.assertIn('pc.bc_words == 2u', SHADER)
        self.assertIn('alphaIndexBC3', SHADER)
        self.assertIn('three_color', SHADER)
        self.assertIn('ALPHA_MOD[8]', SHADER)
        self.assertIn('swap32(high)', SHADER)
        self.assertIn('swap32(low)', SHADER)
        self.assertIn('swap32(alpha_be_hi)', SHADER)
        self.assertIn('swap32(alpha_be_lo)', SHADER)
        self.assertIn('uint x = i / 4u, y = i % 4u;', SHADER)
        self.assertIn('uint bit = 45u - 3u * i;', SHADER)
        self.assertIn('if (block.x >= pc.blocks_x || block.y >= pc.blocks_y) return;', SHADER)
        self.assertIn('add_host_shader(bcn_to_etc2.comp bcn_to_etc2_comp)', CMAKE)

    def test_only_sampled_single_layer_mali_2d_with_supported_etc2(self):
        self.assertIn('GOW3_MALI_BCN_TO_ETC2', IMAGE)
        self.assertIn('vendorID == 0x13B5', IMAGE)
        self.assertIn('info.type == AmdGpu::ImageType::Color2D', IMAGE)
        self.assertIn('info.resources.layers == 1', IMAGE)
        self.assertIn('info.num_samples == 1', IMAGE)
        self.assertIn('info.props.is_block', IMAGE)
        self.assertIn('instance.IsFormatSupported(target, required)', IMAGE)
        self.assertIn('ProbeImageFormat(instance, etc2_info)', IMAGE)
        self.assertIn('format_info = etc2_info', IMAGE)
        self.assertIn('transcoded_bc_to_etc2 = true', IMAGE)
        self.assertIn('flags = {};', IMAGE)
        self.assertIn('usage_flags = target_usage', IMAGE)
        self.assertIn('transcoded_bc_to_etc2 && format == image.info.pixel_format', VIEW)
        self.assertIn('view_format = backing_format', VIEW)

    def test_shader_receives_original_guest_bc_and_uses_gpu_compute(self):
        self.assertIn('BcnTranscodeState', RUNTIME)
        self.assertIn('scratch.buffer->Handle()', RUNTIME)
        self.assertIn('staging.Request(output_bytes, VideoCore::MemoryType::DeviceLocal', RUNTIME)
        self.assertIn('staging.FreeDeferred(scratch)', RUNTIME)
        self.assertIn('cb.dispatch((params.blocks_x + 7u) / 8u', RUNTIME)
        self.assertIn('cb.pipelineBarrier2(barrier)', RUNTIME)
        self.assertIn('cb.copyBufferToImage(scratch_buffer, image', RUNTIME)
        self.assertLess(RUNTIME.index('cb.pipelineBarrier2(barrier)'),
                        RUNTIME.index('cb.copyBufferToImage(scratch_buffer, image'))
        self.assertIn('vk::PipelineStageFlagBits2::eComputeShader', RUNTIME)
        self.assertIn('vk::AccessFlagBits2::eShaderRead', RUNTIME)
        self.assertIn('ASSERT_MSG(recorded', RUNTIME)

    def test_disabled_by_default_no_adreno_change(self):
        self.assertIn('GOW3_MALI_BCN_TO_ETC2=' + '$' + '{GOW3_MALI_BCN_TO_ETC2:-0}', RUN)
        mali = RUN.split('  */libvulkan_panfrost.so)', 1)[1].split(
            '# End Mali PanVK safe profile.', 1)[0]
        self.assertIn('export GOW3_MALI_BCN_TO_ETC2=', mali)
        self.assertNotIn('export GOW3_MALI_BCN_TO_ETC2=', RUN.split(
            '  */libvulkan_panfrost.so)', 1)[0])


if __name__ == "__main__":
    unittest.main()
