"""Verify Bachata RELEASE's non-push descriptor tiling path is retained.

Source comparison: zenithblue-oss/shadps4-arm64, main,
src/video_core/texture_cache/tile_manager.{h,cpp}.
The inaccessible 0.2.5 release-specific source commit is NOT represented as verified.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDR = (ROOT / "gpu/shadps4/video_core/texture_cache/tile_manager.h").read_text()
CPP = (ROOT / "gpu/shadps4/video_core/texture_cache/tile_manager.cpp").read_text()


class BachataMaliTilingDescriptorPort(unittest.TestCase):
    def test_descriptor_layout_uses_capability_not_assumption(self):
        self.assertIn("MaxPushDescriptors() >= 3", CPP)
        self.assertIn("uses_push_descriptors{", CPP)
        self.assertIn("vk::DescriptorSetLayoutCreateFlags{}", CPP)
        self.assertNotIn(
            ".flags = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,",
            CPP,
        )

    def test_non_push_path_binds_normal_descriptor_set(self):
        self.assertIn("Vulkan::DescriptorHeap desc_heap", HDR)
        self.assertIn("tiling_pool_sizes", HDR)
        self.assertIn("desc_heap.Commit(*desc_layout)", CPP)
        self.assertIn("instance.GetDevice().updateDescriptorSets(writes, {})", CPP)
        self.assertIn("cmdbuf.bindDescriptorSets(", CPP)
        self.assertIn("cmdbuf.pushDescriptorSetKHR(", CPP)

    def test_threaded_recorder_owns_descriptor_bindings(self):
        self.assertLess(
            CPP.index("instance.GetDevice().updateDescriptorSets(writes, {})"),
            CPP.index("scheduler.Record([pipeline, layout = *pl_layout"),
        )
        self.assertIn("push = uses_push_descriptors, set", CPP)

    def test_three_descriptors_and_correct_lifetime(self):
        self.assertIn("eStorageBuffer, 128", HDR)
        self.assertIn("eUniformBuffer, 64", HDR)
        self.assertIn("scheduler_.GetWorkSemaphore()", CPP)
        self.assertLess(HDR.index("tiling_pool_sizes"), HDR.index("Vulkan::DescriptorHeap desc_heap"))


if __name__ == "__main__":
    unittest.main()
