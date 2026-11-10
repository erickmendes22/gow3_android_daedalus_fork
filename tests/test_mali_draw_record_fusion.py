"""Mali Vulkan draw recording: preserve command order while fusing record closures."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_common.cpp").read_text()
WORKFLOW = (ROOT / ".github/workflows/gow3-mali-rebind-native-only.yml").read_text()

class RecordFusionTest(unittest.TestCase):
    def test_push_path_records_both_commands_together(self):
        fn = P.split("void Pipeline::BindResources(", 1)[1].split(
            "std::string Pipeline::GetDebugString", 1)[0]
        self.assertIn("if (uses_push_descriptors && !set_writes.empty())", fn)
        self.assertIn("if (!scheduler.IsRecordingDeferred())", fn)
        self.assertIn("scheduler.ReserveRecordData(bytes);", fn)
        self.assertIn("scheduler.RecordData(std::span<const vk::WriteDescriptorSet>{set_writes});", fn)
        self.assertIn("[bind_point, layout, writes, stage_flags, push_data]", fn)
        combined = fn.split("scheduler.Record([bind_point, layout, writes, stage_flags, push_data]", 1)[1].split("});", 1)[0]
        self.assertLess(combined.find("cmdbuf.pushConstants"), combined.find("cmdbuf.pushDescriptorSetKHR"))
        self.assertIn("cmdbuf.pushDescriptorSetKHR(bind_point, layout, 0, writes);", combined)
        self.assertIn("return;", fn.split("cmdbuf.pushDescriptorSetKHR(bind_point, layout, 0, writes);", 1)[1])

    def test_old_non_push_path_still_allocates_and_updates(self):
        self.assertIn("const auto desc_set = desc_heap.Commit(*desc_layout);", P)
        self.assertIn("instance.GetDevice().updateDescriptorSets(set_writes, {});", P)
        self.assertIn("cmdbuf.bindDescriptorSets(bind_point, layout, 0, desc_set, {});", P)
        self.assertIn("if (set_writes.empty())", P)
        self.assertIn("cmdbuf.pushConstants(layout, stage_flags, 0u, sizeof(push_data), &push_data);", P)

    def test_rebind_native_workflow_remains_no_apk(self):
        self.assertIn("test_mali_draw_record_fusion.py", WORKFLOW)
        self.assertIn("vk_pipeline_common.cpp", WORKFLOW)
        self.assertIn("NO APK", WORKFLOW)

if __name__ == "__main__":
    unittest.main()
