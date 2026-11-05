"""Mali PanVK optional Vulkan paths must work without KHR_push_descriptor.

The Bachata public ARM64 copy path uses vkCmdCopyBuffer rather than the
Daedalus compute optimization. The separate GoW3 predication reducer gains
ordinary descriptor sets on drivers lacking the extension.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HLE = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_shader_hle.cpp").read_text()
PRED = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_predication.cpp").read_text()
HDR = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_predication.h").read_text()


class MaliNoPush(unittest.TestCase):
    def test_bachata_copy_fallback_without_extension(self):
        self.assertIn("instance.MaxPushDescriptors() < 3", HLE)
        self.assertIn("return false;", HLE[HLE.index("MaxPushDescriptors() < 3"):][:120])
        self.assertLess(HLE.index("MaxPushDescriptors() < 3"), HLE.index("static Pipeline pipe"))

    def test_predication_layout_is_not_unconditional_push(self):
        self.assertIn("if (instance.MaxPushDescriptors() < 2)", PRED)
        self.assertIn("vk::DescriptorSetLayoutCreateFlags{}", PRED)
        self.assertIn("std::unique_ptr<DescriptorHeap> reduce_heap", HDR)
        self.assertIn("scheduler.GetWorkSemaphore()", PRED)

    def test_predication_fallback_binds_set_on_recorder_thread(self):
        self.assertIn("reduce_heap->Commit(*reduce_desc_layout)", PRED)
        self.assertIn("instance.GetDevice().updateDescriptorSets(set_writes, {})", PRED)
        self.assertIn("cmdbuf.bindDescriptorSets(", PRED)
        self.assertIn("cmdbuf.pushDescriptorSetKHR(", PRED)
        self.assertLess(PRED.index("updateDescriptorSets(set_writes, {})"),
                        PRED.rindex("scheduler.Record([=](vk::CommandBuffer cmdbuf)"))
        self.assertLess(HDR.index("reduce_pool_sizes"), HDR.index("reduce_heap;"))


if __name__ == "__main__":
    unittest.main()
