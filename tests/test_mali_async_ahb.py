"""Mali/PanVK async readback is fence-safe and does not change other GPUs.

These are source-contract checks. They do not claim to measure GoW3 FPS.
"""
from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRESENTER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
HEADER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.h")
RUNNER = (ROOT / "tools/android/bionic/run-bionic.sh")


class MaliAsyncPresentTests(unittest.TestCase):
    def test_only_cpu_present_on_mali_uses_async_worker(self):
        body = PRESENTER.read_text()
        self.assertIn('std::getenv("GOW3_MALI_ASYNC_PRESENT")', body)
        self.assertIn('mali_cpu_async = swapchain.UsesCpuPresentation() &&', body)
        self.assertIn('vendorID == 0x13B5', body)
        self.assertIn('if (!defer_acquire && !swapchain.AcquireNextImage())', body)
        self.assertIn('if (mali_cpu_async) {', body)
        self.assertIn('CompleteMaliCpuPresentation(job);', body)

    def test_readback_has_per_frame_storage_and_no_device_idle(self):
        body = PRESENTER.read_text()
        header = HEADER.read_text()
        self.assertIn('VkBuffer mali_cpu_readback{VK_NULL_HANDLE};', header)
        self.assertIn('VmaAllocation mali_cpu_readback_allocation{};', header)
        self.assertIn('frame->mali_cpu_readback_size = required;', body)
        self.assertIn('vk::Buffer{frame->mali_cpu_readback}', body)
        self.assertNotIn('MALI_CPU_PRESENT cannot retire the old staging buffer', body)

    def test_worker_preserves_fence_order_and_frame_lifetime(self):
        body = PRESENTER.read_text()
        header = HEADER.read_text()
        self.assertIn('std::jthread mali_cpu_worker;', header)
        self.assertIn('std::deque<MaliCpuPresentJob> mali_cpu_jobs;', header)
        self.assertIn('mali_cpu_inflight', header)
        self.assertIn('mali_cpu_jobs_cv.wait(lock, [&]', body)
        self.assertIn('work', body.lower())
        wait = body.index('waitForFences(frame->present_done, true, ~0ull);',
                          body.index('void Presenter::CompleteMaliCpuPresentation'))
        invalidate = body.index('vmaInvalidateAllocation', wait)
        delivery = body.index('swapchain.PresentCpuPixels(', invalidate)
        release = body.index('free_queue.push(frame);', delivery)
        self.assertLess(wait, invalidate)
        self.assertLess(invalidate, delivery)
        self.assertLess(delivery, release)
        self.assertIn('mali_cpu_worker.join();', body)
        self.assertIn('mali_cpu_jobs_cv.notify_all();', body)
        self.assertIn('mali_cpu_inflight[frame->id] == 0', body)

    def test_ahb_resize_is_serialized_with_worker(self):
        body = PRESENTER.read_text()
        self.assertIn('mali_cpu_swapchain_mutex', body)
        self.assertIn('if (resize_needed || next_vsync != mali_cpu_last_vsync)', body)
        self.assertIn('std::scoped_lock lock{mali_cpu_swapchain_mutex};', body)
        self.assertIn('mali_cpu_last_vsync = next_vsync;', body)
        self.assertIn('mali_cpu_last_vsync = Gow3Settings::Get().vsync.load();', body)

    @staticmethod
    def launch_profile(driver, overrides=None):
        text = RUNNER.read_text()
        block = 'case "${GOW3_VULKAN_DRIVER:-}" in' + text.split(
            'case "${GOW3_VULKAN_DRIVER:-}" in', 1
        )[1].split('# End Mali PanVK safe profile.', 1)[0]
        env = dict(os.environ)
        env.update(GOW3_VULKAN_DRIVER=driver, GOW3_MALI_AUTOCAPTURE="0",
                   GOW3_MALI_CPU_SNAPSHOTS="0")
        for key in ("GOW3_MALI_SAFE_MODE", "GOW3_MALI_ASYNC_PRESENT",
                    "PANVK_KBASE_GPU_SEMAPHORE_WAITS",
                    "PANVK_KBASE_SKIP_HEAP_OPS", "PANVK_ZS_PRELOAD_ALWAYS"):
            env.pop(key, None)
        env.update(overrides or {})
        script = block + """
printf 'MALI_FLAGS=%s:%s:%s:%s' \\
  "${GOW3_MALI_ASYNC_PRESENT:-unset}" \\
  "${PANVK_KBASE_GPU_SEMAPHORE_WAITS:-unset}" \\
  "${PANVK_KBASE_SKIP_HEAP_OPS:-unset}" \\
  "${PANVK_ZS_PRELOAD_ALWAYS:-unset}"
"""
        result = subprocess.run(["sh", "-eu", "-c", script], env=env,
                                capture_output=True, text=True, check=True)
        return result.stdout.split('MALI_FLAGS=', 1)[1]

    def test_bachata_v3_defaults_apply_only_to_panvk(self):
        self.assertEqual(
            self.launch_profile("/data/app/libvulkan_panfrost.so"), "1:1:0:0")
        self.assertEqual(
            self.launch_profile("/data/app/libvulkan_freedreno.so"),
            "unset:unset:unset:unset")
        self.assertEqual(
            self.launch_profile("/system/libvulkan.so"),
            "unset:unset:unset:unset")

    def test_fallback_does_not_force_mali_options(self):
        self.assertEqual(
            self.launch_profile("/data/app/libvulkan_panfrost.so",
                                {"GOW3_MALI_SAFE_MODE": "0"}),
            "unset:unset:unset:unset")
        self.assertEqual(
            self.launch_profile("/data/app/libvulkan_panfrost.so",
                                {"GOW3_MALI_ASYNC_PRESENT": "0",
                                 "PANVK_KBASE_GPU_SEMAPHORE_WAITS": "0",
                                 "PANVK_KBASE_SKIP_HEAP_OPS": "1",
                                 "PANVK_ZS_PRELOAD_ALWAYS": "1"}),
            "0:0:1:1")


if __name__ == "__main__":
    unittest.main()
