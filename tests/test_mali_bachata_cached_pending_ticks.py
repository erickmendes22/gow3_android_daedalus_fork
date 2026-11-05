"""Bachata-style Mali completed-tick reclamation safeguards."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
S = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text()
P = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_mali_perf_stats.h").read_text()
RUN = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()

class CachedPendingTickTests(unittest.TestCase):
    def test_scope_and_rollback(self):
        for flag in ("GOW3_MALI_CACHED_PENDING_TICKS", "GOW3_ANDROID_PORT",
                     "GOW3_VK_POLL_EACH_SUBMIT", "vendorID == 0x13B5"):
            self.assertIn(flag, S)
        self.assertIn("GOW3_MALI_CACHED_PENDING_TICKS=${GOW3_MALI_CACHED_PENDING_TICKS:-1}", RUN)

    def test_retire_only_after_confirmed_tick(self):
        pop = S.split("void Scheduler::PopPendingOperations()", 1)[1].split(
            "void Scheduler::AllocateWorkerCommandBuffers()", 1)[0]
        self.assertLess(pop.index("if (mali_cached_pending_ticks)"),
                        pop.index("work_semaphore.Refresh();"))
        self.assertIn("work_semaphore.IsFree(pending_ops.front().gpu_tick)", pop)
        self.assertIn("work_semaphore.Wait(signal_value - MaxAndroidInFlightSubmissions)", S)
        self.assertIn("work_semaphore.Wait(tick);", S)

    def test_legacy_poll_is_measurable(self):
        self.assertIn("MaliPerfStats::Stage::PendingTimelineQuery", S)
        self.assertIn("PendingTimelineQuery", P)
        self.assertIn('"pending_timeline_query"', P)

if __name__ == "__main__":
    unittest.main()
