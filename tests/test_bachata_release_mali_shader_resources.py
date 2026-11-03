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

    def test_preloaded_fixed_mip_descriptor_count_never_reads_guest_sharp(self):
        self.assertIn(
            "if (mip_fallback_mode != MipStorageFallbackMode::DynamicIndex)",
            SRC,
        )
        num_bindings = SRC.split("u32 NumBindings(", 1)[1].split("\\n};", 1)[0]
        self.assertLess(num_bindings.find("return 1;"), num_bindings.find("GetSharp(info)"))
        self.assertIn("tsharp.last_level >= tsharp.base_level", num_bindings)

    def test_dynamic_mip_pipelines_defer_until_live_guest_state(self):
        serialization = (
            Path(__file__).resolve().parents[1]
            / "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp"
        ).read_text()
        self.assertIn("NeedsLiveImageSharpForLayout(sel.infos[0])", serialization)
        self.assertIn("std::ranges::any_of(sel.infos, NeedsLiveImageSharpForLayout)", serialization)
        self.assertIn("std::ranges::any_of(infos, NeedsLiveImageSharpForLayout)", serialization)

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
