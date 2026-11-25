from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
V=ROOT/"gpu/shadps4/video_core/renderer_vulkan"
class TickPriority(unittest.TestCase):
    def test_wait_confirmed_before_reuse(self):
        b=(V.parent/"buffer_cache/buffer.cpp").read_text()
        s=b.split("bool StreamBuffer::WaitPendingOperations",1)[1]
        self.assertIn("std::max(required_tick, watch.tick)",s)
        self.assertLess(s.index("scheduler.Wait(required_tick)"),s.index("wait_cursor = next_cursor"))
        self.assertIn("!allow_wait && !scheduler.IsFree(required_tick)",s)
        self.assertNotIn("scheduler.Wait(watch.tick)",s)
    def test_completed_tick_and_unsubmitted_query(self):
        s=(V/"vk_scheduler.cpp").read_text()
        self.assertIn("if (work_semaphore.IsFree(tick)) return;",s)
        h=(V/"vk_scheduler.h").read_text()
        self.assertIn("if (tick >= work_semaphore.CurrentTick()) return false;",h)
        sem=(V/"vk_semaphore.cpp").read_text()
        self.assertIn("ASSERT_MSG(result == vk::Result::eSuccess",sem)
        self.assertIn("!opt || opt[0] != '0'",sem)
    def test_no_elision_of_incoming_clears(self):
        s=(V/"vk_scheduler.cpp").read_text()
        self.assertIn("if (!incoming.color_attachments[i].is_clear)",s)
        self.assertIn("if (!b.depth_clear)",s)
        self.assertIn("if (!b.stencil_clear)",s)
        self.assertIn("if (previous == incoming)",s)
        self.assertIn("EndRendering();",s)
    def test_profile_keeps_expensive_capture_off(self):
        d=(V/"vk_wait_diagnostics.h").read_text()
        self.assertIn('std::getenv("GOW3_MALI_GPU_TICK_PROFILE")',d)
        self.assertIn("if (!TickProfileEnabled()) return;",d)
        sh=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()
        self.assertIn('GOW3_VK_MAX_IN_FLIGHT:-2',sh)
        self.assertIn('GOW3_MALI_SHADER_STAGE_BARRIERS:-1',sh)
    def test_bulk_upload_keeps_completion_epoch(self):
        pool=(ROOT/"gpu/shim/gow3_copy.cpp").read_text()
        code=pool.split("    void AsyncItems(std::span<const Item> items)",1)[1].split("    void AfterCopies(",1)[0]
        self.assertIn("std::scoped_lock lk{mutex}",code)
        self.assertIn("epochs.back().pending += items.size();",code)
        self.assertIn("pending += items.size();",code)
        self.assertIn("cv.notify_all();",code)
        buf=(V.parent/"buffer_cache/buffer_cache.cpp").read_text()
        self.assertIn("Gow3Copy::AsyncItems(large_copies);",buf)
    def test_guest_finish_site_preserved(self):
        self.assertIn("scheduler.Finish(caller);",(V/"vk_rasterizer.cpp").read_text())
    def test_clear_value_uses_compatible_array_assignment(self):
        r=(V/"vk_rasterizer.cpp").read_text()
        self.assertIn("is_clear ? LiverpoolToVK::ColorBufferClearValue(col_buf) : vk::ClearValue{}",r)
        self.assertIn("attachment.clear_value = clear_value.color.uint32;",r)
        self.assertNotIn("is_clear ? clear_value.color.uint32 :",r)
if __name__=="__main__": unittest.main()
