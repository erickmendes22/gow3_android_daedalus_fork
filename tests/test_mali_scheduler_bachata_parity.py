"""PanVK vs Bachata: do not force a GPU drain every two submissions.

Regression verifies the prior renderer's explicit fences, a bounded 4-deep
Mali timeline with =2 rollback, and the lightweight wall-clock counters.
The key question is how much of a >100 ms menu frame is spent in the
submission throttle, NOT the sub-millisecond CPU AHB copy.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
S = (ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text()
P = (ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_mali_perf_stats.h").read_text()
L = (ROOT/"tools/android/bionic/run-bionic.sh").read_text()

class MaliSchedulerBachataParityTests(unittest.TestCase):
    def test_bounded_queue_and_rollbacks(self):
        self.assertIn("GOW3_VK_MAX_IN_FLIGHT=${GOW3_VK_MAX_IN_FLIGHT:-4}", L)
        self.assertIn("=2 restores the stable cap", L)
        self.assertIn("requested >= 1 && requested <= 8", S)
        self.assertIn("work_semaphore.Wait(signal_value - MaxAndroidInFlightSubmissions)", S)
        self.assertIn("export GOW3_FRAMES_AHEAD=1", L)
        self.assertIn("export GOW3_DEFERRED_READBACK=0", L)
        self.assertIn("export GOW3_MALI_CPU_PRESENT=${GOW3_MALI_CPU_PRESENT:-1}", L)

    def test_measure_gpu_queue_stalls_without_profiler_thread(self):
        self.assertIn("MaliPerfStats::Stage::SubmitThrottle", S)
        self.assertIn("MaliPerfStats::Stage::SubmitHostCopies", S)
        self.assertIn("MaliPerfStats::Stage::SubmitMutex", S)
        self.assertIn("MaliPerfStats::Stage::SubmitQueueDriver", S)
        self.assertIn("MaliPerfStats::SampleSubmit()", S)
        self.assertIn("(++submits & 31u) == 0", P)
        self.assertIn('"submit_throttle"', P)
        self.assertIn('"submit_vk_queue"', P)
        self.assertIn("MaliPerfStats::ReportIfDue()", (ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text())
        self.assertIn("if (mali_timing)", S)
        self.assertNotIn("vkCmdWriteTimestamp", S)

if __name__=="__main__":
    unittest.main()
