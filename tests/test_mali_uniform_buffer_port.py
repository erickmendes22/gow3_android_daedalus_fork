"""Static safety gate for the isolated read-only shader UBO experiment.

This does not claim measured Mali FPS or replace the real ARM64 renderer build.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
def read(name):
    return (ROOT / name).read_text(encoding="utf-8")

class MaliUniformBufferPort(unittest.TestCase):
    def test_enabled_by_default_and_minimum_vulkan_range(self):
        s = read("gpu/shadps4/shader_recompiler/info.h")
        self.assertIn('std::getenv("GOW3_UBO")', s)
        self.assertRegex(s, r"env\[0\] - '0' : 2;")
        self.assertIn("MaxUniformBufferBytes = 16384", s)
        self.assertIn("return bytes >= 4 && bytes <= MaxUniformBufferBytes;", s)
        self.assertIn("desc.is_written ||", s)
        self.assertIn("desc.is_formatted ||", s)
        self.assertLess(s.index("if (!stage_ok || desc.buffer_type"), s.index("desc.GetSharp(info).GetSize()"))
        self.assertIn("BufferType::Guest", s)
        self.assertIn("SwStage::Vertex", s)
        self.assertIn("SwStage::Fragment", s)

    def test_shader_and_descriptor_agreement(self):
        emitter = read("gpu/shadps4/shader_recompiler/backend/spirv/spirv_emit_context.cpp")
        gfx = read("gpu/shadps4/video_core/renderer_vulkan/vk_graphics_pipeline.cpp")
        bind = read("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        self.assertIn("UseUniformBuffer(info, desc)", emitter)
        self.assertIn("spv::StorageClass::Uniform", emitter)
        self.assertIn("TypeArray(data_type", emitter)
        self.assertIn("key.uniform_buffer_masks[stage_index]", gfx)
        self.assertIn("vk::DescriptorType::eUniformBuffer", gfx)
        self.assertIn("bool(bind_ubo_masks[u32(stage.sw_stage)]", bind)
        self.assertIn("vk::DescriptorType::eUniformBuffer", bind)
        self.assertIn("UniformMinAlignment()", bind)
        self.assertIn("MaxUniformBufferBytes", bind)
        self.assertIn("std::memset(dst + size, 0, reserve - size)", bind)
        self.assertIn("constant_ring->Flush(*offset, reserve)", bind)

    def test_preloaded_pipeline_never_dereferences_invalid_guest_sharps(self):
        hdr = read("gpu/shadps4/video_core/renderer_vulkan/vk_graphics_pipeline.h")
        gfx = read("gpu/shadps4/video_core/renderer_vulkan/vk_graphics_pipeline.cpp")
        cache = read("gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp")
        bind = read("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        raster_h = read("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.h")
        self.assertIn("std::array<u64, MaxShaderStages> uniform_buffer_masks;", hdr)
        self.assertIn("key.uniform_buffer_masks[stage_out_idx] = uniform_mask;", cache)
        self.assertIn("if (Shader::UseUniformBuffer(*live_info, live_info->buffers[i]))", cache)
        builder = gfx[gfx.index("void GraphicsPipeline::BuildDescSetLayout("):]
        self.assertIn("const u64 uniform_mask = key.uniform_buffer_masks[stage_index];", builder)
        self.assertIn("bool(uniform_mask & (u64{1} << buffer_index))", builder)
        self.assertNotIn("buffer.GetSharp(*stage)", builder)
        self.assertNotIn("UseUniformBuffer(*stage, buffer)", builder)
        self.assertIn("std::array<u64, MaxShaderStages> bind_ubo_masks{};", raster_h)
        self.assertIn("GetGraphicsKey().uniform_buffer_masks", bind)
        self.assertIn("bool(bind_ubo_masks[u32(stage.sw_stage)]", bind)
        self.assertIn("void GraphicsPipelineKey::Serialize(", read(
            "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp"))
        self.assertIn("key.Write(this, sizeof(*this));", read(
            "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp"))

    def test_std430_ubo_requires_enabled_device_feature(self):
        info = read("gpu/shadps4/shader_recompiler/info.h")
        instance = read("gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp")
        profile = read("gpu/shadps4/shader_recompiler/profile.h")
        cache = read("gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp")
        self.assertIn("uniform_std430_supported{false}", info)
        self.assertIn("if (!UniformBufferStandardLayoutSupported()) return false;", info)
        self.assertIn("SetUniformBufferStandardLayoutSupported(", instance)
        self.assertIn("vk12_features.uniformBufferStandardLayout == VK_TRUE", instance)
        self.assertIn(".uniformBufferStandardLayout = vk12_features.uniformBufferStandardLayout", instance)
        self.assertIn("supports_uniform_buffer_std430{}", profile)
        self.assertIn(".supports_uniform_buffer_std430 = instance_.IsUniformBufferStandardLayoutSupported()", cache)
        self.assertIn("GOW3_UBO_DEVICE", instance)
        self.assertIn("properties.limits.minUniformBufferOffsetAlignment <= 256", instance)
        launcher = read("tools/android/bionic/run-bionic.sh")
        self.assertIn("GOW3_UBO=${GOW3_UBO:-2}", launcher)
        self.assertIn("ubo=$GOW3_UBO", launcher)

    def test_stage_rings_and_direct_bindings_use_pipeline_masks(self):
        hdr = read("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.h")
        bind = read("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        self.assertIn("u64 uniform_mask,", hdr)
        self.assertIn("CollectRingBindings(*stage, used_prepared, uniform_mask, ring);", bind)
        self.assertIn("uniform_mask & (u64{1} << index)", bind)
        self.assertIn("const bool uniform = bool(bind_ubo_masks[u32(stage.sw_stage)]", bind)
        self.assertIn("const u64 bound_range = uniform", bind)
        self.assertIn("Shader::UniformBufferSizeLog2(ring->size)", bind)
        self.assertIn("offset, uniform ? std::max<u64>(alignment, instance.UniformMinAlignment())", bind)
        self.assertIn("constant_ring->Flush(*offset, reserve)", bind)

    def test_specialization_tracks_declared_range_and_cache_invalidated(self):
        spec = read("gpu/shadps4/shader_recompiler/specialization.h")
        serial = read("gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp")
        self.assertIn("ubo_size_log2", spec)
        self.assertIn("UniformBufferSizeLog2(sharp.GetSize())", spec)
        self.assertIn("ubo_size_log2 == other.ubo_size_log2", spec)
        self.assertIn("Shader::UniformBufferLevel()", serial)
        self.assertIn("ShaderBinaryVersion = 8u", serial)
        self.assertIn("ShaderMetaVersion = 9u", serial)
        self.assertIn("PipelineKeyVersion = 7u", serial)

if __name__ == "__main__":
    unittest.main()
