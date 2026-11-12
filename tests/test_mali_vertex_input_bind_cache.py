"""Mali exact vertex-input cache: no state elision across incompatible bindings."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"gpu/shadps4/video_core/renderer_vulkan"
S=(DIR/"vk_scheduler.cpp").read_text()
H=(DIR/"vk_scheduler.h").read_text()
D=(DIR/"vk_rasterizer.cpp").read_text()
P=(DIR/"vk_mali_perf_stats.h").read_text()

class VertexInputBindCache(unittest.TestCase):
    def test_exact_fields_with_opt_out_and_driver_call(self):
        self.assertIn('GOW3_MALI_VERTEX_INPUT_CACHE',S)
        self.assertIn('cmdbuf.setVertexInputEXT(bindings, attributes);',S)
        self.assertIn('cmdbuf == last_vertex_input_cmd',S)
        for member in ('a.binding == b.binding', 'a.stride == b.stride',
                       'a.inputRate == b.inputRate', 'a.divisor == b.divisor',
                       'a.location == b.location','a.format == b.format',
                       'a.offset == b.offset', 'a.sType == b.sType',
                       '!a.pNext && !b.pNext'):
            self.assertIn(member,S)
        self.assertIn('scheduler.SetVertexInputCached(cmdbuf, bindings, attributes);',D)
        self.assertIn('CountVertexInputSet(true)',S)
        self.assertIn('CountVertexInputSet(false)',S)
        self.assertIn('vertex_input_skipped=%llu',P)

    def test_all_graphics_and_raw_invalidations(self):
        bind=S.split('void Scheduler::BindGraphicsPipelineCached(',1)[1].split(
            'void Scheduler::AllocateWorkerCommandBuffers()',1)[0]
        self.assertIn('last_vertex_input_cmd = vk::CommandBuffer{};',bind)
        allocate=S.split('void Scheduler::AllocateWorkerCommandBuffers()',1)[1]
        self.assertIn('last_vertex_input_cmd = vk::CommandBuffer{};',allocate)
        raw=H.split('vk::CommandBuffer CommandBuffer()',1)[1].split(
            '/// GOW3_RECORDER_TRACE',1)[0]
        self.assertIn('last_vertex_input_cmd = vk::CommandBuffer{};',raw)
        self.assertIn('last_vertex_input_bindings',H)
        self.assertIn('last_vertex_input_attributes',H)

    def test_cpu_command_fusion_is_kept(self):
        self.assertIn('scheduler.Record([this, dynamic_input, num_buffers, bindings, attributes', D)
        # The deferred lambda invokes a Rasterizer member; capture must be explicit.
        self.assertIn('scheduler.SetVertexInputCached(cmdbuf, bindings, attributes);', D)
        self.assertIn('cmdbuf.bindVertexBuffers2(0, num_buffers, buffers.data(), offsets.data()',D)
        self.assertIn('cmdbuf.bindIndexBuffer(index_handle, index_offset, index_type)',D)

if __name__=="__main__": unittest.main()
