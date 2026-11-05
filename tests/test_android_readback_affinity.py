"""Regression guard for the bounded Vulkan timeline and safe CPU thread policy."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ReadbackAffinityTests(unittest.TestCase):
    def test_bounded_gpu_submission_without_per_submit_query(self):
        code = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text()
        start = code.index("void Scheduler::SubmitExecution(SubmitInfo& info)")
        end = code.index("\nvoid Scheduler::PriorityPendingOpsThread", start)
        submit = code[start:end]
        # Default stays at 8 for Adreno/desktop. A Mali PanVK-only runner
        # can opt in to 2 via GOW3_VK_MAX_IN_FLIGHT.
        self.assertIn('std::getenv("GOW3_VK_MAX_IN_FLIGHT")', submit)
        self.assertIn("return u64{8};", submit)
        self.assertIn("requested >= 1 && requested <= 8", submit)
        self.assertIn('std::getenv("GOW3_ANDROID_PORT")', submit)
        self.assertIn('std::getenv("GOW3_VK_POLL_EACH_SUBMIT")', submit)
        self.assertIn("work_semaphore.Wait(signal_value - MaxAndroidInFlightSubmissions)", submit)
        self.assertIn("if (!bounded_submit) {\n        work_semaphore.Refresh();", submit)
        self.assertEqual(submit.count("work_semaphore.Refresh();"), 1)
        self.assertIn("PopPendingOperations();", submit)

    def test_demand_readbacks_still_block_until_valid(self):
        scheduler = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text()
        buffer_cache = (ROOT / "gpu/shadps4/video_core/buffer_cache/buffer_cache.cpp").read_text()
        texture_cache = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()
        self.assertIn("work_semaphore.Wait(tick);", scheduler)
        self.assertIn("scheduler.Finish();", buffer_cache)
        self.assertIn("scheduler.Finish();", texture_cache)
        self.assertIn("ResolveReadbacks(", texture_cache)
        self.assertIn("has_pending_readbacks.store(true", texture_cache)
        self.assertIn("pending_readbacks.Push(", texture_cache)

    def test_empty_download_queue_skips_host_copy_barrier(self):
        code = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()
        begin = code.index("void TextureCache::ProcessDownloadImages()")
        end = code.index("std::optional<TextureCache::PendingDownload>", begin)
        method = code[begin:end]
        empty = method.index("if (!has_new_downloads)")
        wait = method.index("scheduler.WaitHostCopies();")
        self.assertLess(empty, wait)
        self.assertIn("download_images_mutex", method[:wait])
        self.assertIn("has_pending_readbacks.load(std::memory_order_acquire)", method[:wait])
        self.assertIn("RetireReadbacks();", method[:wait])
        self.assertIn("return;", method[empty:wait])
        # If a copy will be enqueued, host workers MUST finish before a
        # guest page is protected for the GPU transfer.
        self.assertLess(wait, method.index("WatchReadback<true>"))
        self.assertLess(wait, method.index("pending_readbacks.Push("))

    def test_cpu_guest_affinity_remains_semantic_not_host_pinning(self):
        runtime = (ROOT / "src/runtime_thread.c").read_text()
        self.assertIn("t->attr.affinity=mask", runtime)
        self.assertIn("*mask=t->attr.affinity", runtime)
        self.assertNotIn("pthread_setaffinity_np(", runtime)
        self.assertNotIn("sched_setaffinity(", runtime)

if __name__ == "__main__":
    unittest.main()
