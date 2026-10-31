"""Bachata S4 label-generation retirement semantics on PanVK only."""
from pathlib import Path
import unittest

R = Path(__file__).resolve().parents[1]
def read(p):
    return (R / p).read_text()

class FlipRetirementTests(unittest.TestCase):
    def test_source_has_generation_and_vblank_guard(self):
        header = read("gpu/shadps4/core/libraries/videoout/flip_label_tracker.h")
        self.assertIn("RecordGpuLock", header)
        self.assertIn("ScheduleRetirement", header)
        self.assertIn("ConsumeDueRetirement", header)
        self.assertIn("generations[static_cast<size_t>(consumed.index)] != consumed.generation", header)
    def test_panvk_only_runtime_gate(self):
        runner = read("tools/android/bionic/run-bionic.sh")
        self.assertIn('*/libvulkan_panfrost.so)', runner)
        self.assertIn("export GOW3_VIDEOOUT_LABEL_RETIRE=1", runner)
        driver = read("gpu/shadps4/core/libraries/videoout/driver.cpp")
        self.assertIn('std::getenv("GOW3_VIDEOOUT_LABEL_RETIRE")', driver)
        self.assertIn("if (main_port.retire_labels_on_vblank) ApplyDueLabelRetirement();", driver)
    def test_gpu_pm4_fence_wait_is_bounded_for_panvk(self):
        cpp = read("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
        self.assertIn("std::this_thread::get_id() == liverpool->GetGpuCommandProcessorThread()", cpp)
        self.assertIn("if (nonblock) {", cpp)
        self.assertIn("if (!available()) return nullptr;", cpp)
        self.assertIn("1'000'000ull", cpp)
        self.assertIn("free_queue.push(frame);", cpp)

    def test_deferred_retry_is_vblank_paced(self):
        cpp = read("gpu/shadps4/core/libraries/videoout/driver.cpp")
        self.assertIn("void VideoOutDriver::RetryDeferredFlip()", cpp)
        self.assertIn("if (!frame)", cpp)
        self.assertIn("if (is_retry) deferred_flips.push_front(item);", cpp)
        self.assertIn("RetryDeferredFlip();", cpp)
        self.assertNotIn("liverpool->EnqueueCommand(", cpp)

    def test_irq_tracks_generation(self):
        video = read("gpu/shadps4/core/libraries/videoout/video_out.cpp")
        self.assertIn("port->flip_labels.Generation", video)
        self.assertIn("driver->SubmitFlip(port, buf_id, flip_arg, true, generation)", video)
        driver = read("gpu/shadps4/core/libraries/videoout/driver.cpp")
        self.assertIn("port->flip_labels.ScheduleRetirement", driver)
        self.assertIn("port->flip_labels.CancelRetirementForIndex", driver)
        self.assertIn("main_port.SignalVoLabel()", driver)
    def test_gpu_write_recorder_marks_lock(self):
        code = read("gpu/shadps4/video_core/amdgpu/liverpool.cpp")
        self.assertIn("MaybeRecordVideoOutLabelLock(vo_port, write_data->Address<u64*>()", code)
        self.assertIn("port->flip_labels.RecordGpuLock", code)

if __name__ == "__main__":
    unittest.main()
