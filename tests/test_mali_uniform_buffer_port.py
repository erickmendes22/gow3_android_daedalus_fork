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
    def test_opt_in_only_and_minimum_vulkan_range(self):
        s = read("gpu/shadps4/shader_recompiler/info.h")
        self.assertIn('std::getenv("GOW3_UBO")', s)
        self.assertRegex(s, r"env\[0\] - '0' : 0;")
        self.assertIn("MaxUniformBufferBytes = 16384", s)
        self.assertIn("bytes >= 4 && bytes <= MaxUniformBufferBytes", s)
        self.assertIn("!desc.is_written && !desc.is_formatted", s)
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
        self.assertIn("UseUniformBuffer(*stage, buffer)", gfx)
        self.assertIn("vk::DescriptorType::eUniformBuffer", gfx)
        self.assertIn("UseUniformBuffer(stage, desc)", bind)
        self.assertIn("vk::DescriptorType::eUniformBuffer", bind)
        self.assertIn("UniformMinAlignment()", bind)
        self.assertIn("MaxUniformBufferBytes", bind)

    def test_specialization_tracks_declared_range_and_cache_invalidated(self):
        spec = read("gpu/shadps4/shader_recompiler/specialization.h")
        serial = read("gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp")
        self.assertIn("ubo_size_log2", spec)
        self.assertIn("UniformBufferSizeLog2(sharp.GetSize())", spec)
        self.assertIn("ubo_size_log2 == other.ubo_size_log2", spec)
        self.assertIn("Shader::UniformBufferLevel()", serial)
        self.assertIn("ShaderBinaryVersion = 8u", serial)
        self.assertIn("ShaderMetaVersion = 9u", serial)
        self.assertIn("PipelineKeyVersion = 6u", serial)

if __name__ == "__main__":
    unittest.main()
