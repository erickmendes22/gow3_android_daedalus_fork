"""Bachata public ARM64 Vulkan blit descriptor fallback for Mali.
Not a rendering validation; native compilation/hardware are separate.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CPP = (ROOT / "gpu/shadps4/video_core/texture_cache/blit_helper.cpp").read_text()
HDR = (ROOT / "gpu/shadps4/video_core/texture_cache/blit_helper.h").read_text()


class BachataReleaseBlitFallback(unittest.TestCase):
    def test_optional_push_descriptor_layout(self):
        self.assertIn("uses_push_descriptors{instance_.MaxPushDescriptors() >= 1}", CPP)
        self.assertIn("vk::DescriptorSetLayoutCreateFlags{}", CPP)
        self.assertNotIn(
            ".flags = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,",
            CPP,
        )

    def test_both_copy_paths_have_normal_descriptor_sets(self):
        self.assertEqual(
            CPP.count("desc_heap.Commit(*single_texture_descriptor_set_layout)"), 2
        )
        self.assertEqual(
            CPP.count("instance.GetDevice().updateDescriptorSets(ordinary, {})"), 2
        )
        self.assertEqual(CPP.count("cmdbuf.bindDescriptorSets("), 2)
        self.assertEqual(CPP.count("cmdbuf.pushDescriptorSetKHR("), 2)

    def test_allocator_has_gpu_tick_lifetime_and_permanent_pool_sizes(self):
        self.assertIn("Vulkan::DescriptorHeap desc_heap", HDR)
        self.assertIn("blit_pool_sizes", HDR)
        self.assertIn("scheduler_.GetWorkSemaphore()", CPP)
        self.assertLess(HDR.index("blit_pool_sizes"), HDR.index("Vulkan::DescriptorHeap desc_heap"))


if __name__ == "__main__":
    unittest.main()
