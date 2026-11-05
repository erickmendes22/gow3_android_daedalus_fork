"""Bachata public ARM64 post-process fallback contract for Mali/PanVK."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PP_CPP = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/host_passes/pp_pass.cpp").read_text()
PP_H = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/host_passes/pp_pass.h").read_text()
PRESENTER_CPP = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text()
PRESENTER_H = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.h").read_text()


class BachataPostProcess(unittest.TestCase):
    def test_push_descriptors_optional_for_final_composition(self):
        self.assertIn("uses_push_descriptors = instance.MaxPushDescriptors() >= 1;", PP_CPP)
        self.assertIn("vk::DescriptorSetLayoutCreateFlags{}", PP_CPP)
        self.assertIn("desc_heap->Commit(*desc_set_layout)", PP_CPP)
        self.assertIn("device.updateDescriptorSets(normal_writes, {})", PP_CPP)
        self.assertIn("cmdbuf.bindDescriptorSets(", PP_CPP)
        self.assertIn("cmdbuf.pushDescriptorSetKHR(", PP_CPP)
        self.assertNotIn(
            ".flags = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,",
            PP_CPP,
        )

    def test_present_timeline_retains_descriptor_lifetime(self):
        self.assertIn("std::unique_ptr<DescriptorHeap> desc_heap", PP_H)
        self.assertIn("present_scheduler.GetWorkSemaphore()", PP_CPP)
        self.assertIn("pp_pass.Create(instance, present_scheduler", PRESENTER_CPP)
        self.assertLess(
            PRESENTER_H.index("Scheduler present_scheduler;"),
            PRESENTER_H.index("HostPasses::PostProcessingPass pp_pass;")
        )
        self.assertLess(PP_H.index("pp_pool_sizes"), PP_H.index("desc_heap;"))


if __name__ == "__main__":
    unittest.main()
