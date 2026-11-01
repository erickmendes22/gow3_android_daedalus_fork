"""Bachata public ARM64 shader resource capacity port.

Source: zenithblue-oss/shadps4-arm64/src/shader_recompiler/resource.h
This protects real image/sampler descriptor storage, not debug capture code.
"""
from pathlib import Path
import unittest

SRC = (
    Path(__file__).resolve().parents[1]
    / "gpu/shadps4/shader_recompiler/resource.h"
).read_text()
RASTERIZER = (
    Path(__file__).resolve().parents[1]
    / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.h"
).read_text()


class BachataShaderResourceCapacity(unittest.TestCase):
    def test_sampler_limit_matches_bachata_arm64(self):
        self.assertIn("static constexpr u32 NUM_SAMPLERS = 32;", SRC)
        self.assertNotIn("static constexpr u32 NUM_SAMPLERS = 16;", SRC)

    def test_rasterizer_can_bind_both_images_and_samplers(self):
        self.assertIn(
            "Shader::NUM_IMAGES + Shader::NUM_SAMPLERS> image_infos;", RASTERIZER
        )
        self.assertIn(
            "boost::container::small_vector<VideoCore::ImageId, Shader::NUM_IMAGES>",
            RASTERIZER,
        )
        self.assertIn(
            "boost::container::small_vector<ImageBindingInfo, Shader::NUM_IMAGES>",
            RASTERIZER,
        )
        self.assertNotIn(
            "static_vector<vk::DescriptorImageInfo, Shader::NUM_IMAGES> image_infos",
            RASTERIZER,
        )

    def test_image_and_sampler_descriptors_can_grow(self):
        self.assertIn("#include <boost/container/small_vector.hpp>", SRC)
        self.assertIn(
            "boost::container::small_vector<ImageResource, NUM_IMAGES>", SRC
        )
        self.assertIn(
            "boost::container::small_vector<SamplerResource, NUM_SAMPLERS>", SRC
        )
        self.assertIn("static constexpr u32 NUM_IMAGES = 64;", SRC)
        self.assertIn("static constexpr u32 NUM_BUFFERS = 40;", SRC)


if __name__ == "__main__":
    unittest.main()
