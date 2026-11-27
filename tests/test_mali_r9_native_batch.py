from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
V=R/"gpu/shadps4/video_core/renderer_vulkan"
S=(V/"vk_scheduler.cpp").read_text()
H=(V/"vk_scheduler.h").read_text()
I=(V/"vk_instance.cpp").read_text()
D=(V/"vk_rasterizer.cpp").read_text()
T=(V.parent/"texture_cache/texture_cache.cpp").read_text()
class NativeBatch(unittest.TestCase):
    def test_feature_gates(self):
        for x in ("PhysicalDeviceMultiDrawFeaturesEXT","maxMultiDrawCount","VK_EXT_MULTI_DRAW_EXTENSION_NAME","device_chain.unlink<vk::PhysicalDeviceMultiDrawFeaturesEXT>","vkCmdDrawMultiEXT","vkCmdDrawMultiIndexedEXT"):
            self.assertIn(x,I)
        self.assertIn("std::min<u32>(32u",I)
    def test_real_native_commands_and_ordering(self):
        self.assertIn("dispatch.vkCmdDrawMultiIndexedEXT(",S)
        self.assertIn("dispatch.vkCmdDrawMultiEXT(",S)
        self.assertIn("native_draw_count >= native_draw_batch_limit",S)
        self.assertIn("native_first_instance != first_instance",S)
        self.assertIn("last_graphics_resource_key == key",S)
        self.assertIn("FlushNativeDrawBatch(cmdbuf);\n            last_graphics_resource_layout",H)
        for cmd in ("cmdbuf.setVertexInputEXT", "cmdbuf.bindIndexBuffer", "cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics"):
            self.assertIn("FlushNativeDrawBatch(cmdbuf);\n    "+cmd,S)
        self.assertIn("chunk->Execute(current_cmdbuf);",S)
        self.assertIn("FlushNativeDrawBatch(current_cmdbuf);",S)
        for x in ("!square && !zpass_query","!pred.predicated","stage->uses_dma","im.is_written || im.is_atomic"):
            self.assertIn(x,D)
    def test_readbacks_strict_and_timeout_not_completion(self):
        self.assertIn("pending_readbacks.HasSmallReadback(scheduler.CurrentTick(), 64)",T)
        self.assertIn("pending_readbacks.Push(",T)
        self.assertIn("WatchReadback<true>",T)
        sem=(V/"vk_semaphore.cpp").read_text()
        self.assertIn("while (result == vk::Result::eTimeout)",sem)
        self.assertIn("ASSERT_MSG(result == vk::Result::eSuccess",sem)
if __name__=="__main__": unittest.main()
