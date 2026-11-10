"""Safe Mali Vulkan pipeline bind elimination, preserving graphics and compute state."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
V=ROOT/"gpu/shadps4/video_core/renderer_vulkan"
S=(V/"vk_scheduler.cpp").read_text()
H=(V/"vk_scheduler.h").read_text()
R=(V/"vk_rasterizer.cpp").read_text()
SCENE=(V/"vk_scene_resolution.cpp").read_text()
P=(V/"vk_mali_perf_stats.h").read_text()
class BindCache(unittest.TestCase):
    def test_cache_traces_pipeline_by_buffer_and_handle(self):
        self.assertIn("cmdbuf == last_graphics_bind_cmd && pipeline == last_graphics_bind_pipeline",S)
        self.assertIn("cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline);",S)
        self.assertIn("GOW3_MALI_PIPELINE_BIND_CACHE",S)
        self.assertIn("graphics_pipeline_bind_cache_enabled",H)
        self.assertIn("last_graphics_bind_cmd = vk::CommandBuffer{};",S)
        self.assertIn("last_graphics_bind_pipeline = vk::Pipeline{};",S)
    def test_external_raw_commandbuffer_invalidates_cache(self):
        direct=H.split("vk::CommandBuffer CommandBuffer()",1)[1].split("/// GOW3_RECORDER_TRACE",1)[0]
        self.assertIn("last_graphics_bind_cmd = vk::CommandBuffer{};",direct)
        self.assertIn("last_graphics_bind_pipeline = vk::Pipeline{};",direct)
        self.assertIn("return current_cmdbuf;",direct)
    def test_all_renderer_graphics_binds_use_cache(self):
        self.assertIn("scheduler.BindGraphicsPipelineCached(cmdbuf, handle);",R)
        self.assertIn("scheduler.BindGraphicsPipelineCached(cmdbuf, square);",R)
        self.assertIn("scheduler.BindGraphicsPipelineCached(cmdbuf, bound);",R)
        self.assertNotIn("cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics",R)
        self.assertIn("scheduler.BindGraphicsPipelineCached(cmd, pipeline);",SCENE)
        self.assertIn("scheduler.Record([=, this](vk::CommandBuffer cmd)",SCENE)
        self.assertIn("gfx_pipeline_binds_skipped=%llu",P)
    def test_compute_bind_points_unmodified(self):
        self.assertIn("cmdbuf.bindPipeline(vk::PipelineBindPoint::eCompute, handle);",R)
if __name__=="__main__": unittest.main()
