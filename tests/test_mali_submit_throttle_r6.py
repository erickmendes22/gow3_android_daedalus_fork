from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
V=ROOT/"gpu/shadps4/video_core/renderer_vulkan"
S=(V/"vk_scheduler.cpp").read_text().split("void Scheduler::SubmitExecution(SubmitInfo& info)",1)[1].split("void Scheduler::PriorityPendingOpsThread",1)[0]
H=(V/"vk_scheduler.h").read_text()
RUN=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()
class SubmitThrottleR6(unittest.TestCase):
    def test_single_stable_reservation_no_global_wait(self):
        self.assertIn("std::mutex mali_submission_order_mutex;",H)
        self.assertLess(S.index("order.lock();"),S.index("std::unique_lock lk{submit_mutex}"))
        self.assertIn("? work_semaphore.CurrentTick() : work_semaphore.NextTick()",S)
        self.assertLess(S.index("lk.unlock();"),S.index("work_semaphore.Wait(signal_value - MaxAndroidInFlightSubmissions)"))
        self.assertLess(S.index("work_semaphore.Wait(signal_value - MaxAndroidInFlightSubmissions)"),S.index("lk.lock();"))
        self.assertLess(S.index("lk.lock();"),S.index("const auto reserved = work_semaphore.NextTick();"))
        self.assertLess(S.index("const auto reserved = work_semaphore.NextTick();"),S.index("GetGraphicsQueue().submit"))
        self.assertNotIn("while (",S)
        self.assertIn("reserved == signal_value",S)
    def test_wait_count_and_driver_fallback(self):
        self.assertIn("Gow3Stats::WaitTimer timer{Gow3Stats::tick_wait_ns}",S)
        self.assertIn('WaitDiagnostics::Get().Add("submit_throttle", 0, 0, elapsed)',S)
        self.assertIn("GOW3_MALI_UNLOCKED_SUBMIT_THROTTLE:-1",RUN)
        self.assertIn("PANVK_KBASE_GPU_SEMAPHORE_WAITS:-0",RUN)
        self.assertIn("GOW3_VK_MAX_IN_FLIGHT:-2",RUN)
    def test_failure_reports_original_wait_site(self):
        sem=(V/"vk_semaphore.cpp").read_text()
        self.assertIn("caller.file_name(), caller.line(), caller.function_name()",sem)
        self.assertIn("ASSERT_MSG(result == vk::Result::eSuccess",sem)
    def test_texture_cache_integrity_preserved(self):
        for flag in ("GOW3_MALI_REBIND_RETIRED_MEMORY","GOW3_MALI_BC_ALIAS_RETIRE","GOW3_MALI_EAGER_COMPLETED_RETIRE","GOW3_TEXTURE_HELPER"):
            self.assertIn(flag+":-0",RUN)
        self.assertIn("GOW3_DEFERRED_READBACK:-1",RUN)
        self.assertIn("export GOW3_STALE_READBACK=0",RUN)
if __name__=="__main__": unittest.main()
