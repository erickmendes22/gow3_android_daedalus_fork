"""Mali driver-specific stability defaults must not affect other GPUs."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/android/bionic/run-bionic.sh"
SCHEDULER = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp"


class MaliPanvkSafetyTests(unittest.TestCase):
    def profile(self, driver, safe=None):
        source = RUNNER.read_text()
        block = 'case "${GOW3_VULKAN_DRIVER:-}" in' + source.split(
            'case "${GOW3_VULKAN_DRIVER:-}" in', 1
        )[1].split("# End Mali PanVK safe profile.", 1)[0]
        env = dict(os.environ)
        env["GOW3_VULKAN_DRIVER"] = driver
        # This unit test executes only the isolated shell profile with no
        # app-private runtime path ($base). Keep expensive BMP capture off here;
        # the actual experimental PanVK launcher defaults it on.
        env["GOW3_MALI_AUTOCAPTURE"] = "0"
        env["GOW3_MALI_CPU_SNAPSHOTS"] = "0"
        env.pop("GOW3_MALI_SAFE_MODE", None)
        if safe is not None:
            env["GOW3_MALI_SAFE_MODE"] = safe
        script = block + """
printf 'RESULT=%s:%s:%s:%s:%s:%s' \
    "${GOW3_GPU_COMPILER_WORKERS:-unset}" "${GOW3_BACKGROUND_WARMUP:-unset}" \
    "${GOW3_VK_MAX_IN_FLIGHT:-unset}" "${GOW3_FRAMES_AHEAD:-unset}" \
    "${GOW3_DEFERRED_READBACK:-unset}" "${GOW3_STALE_READBACK:-unset}"
"""
        run = subprocess.run(["sh", "-eu", "-c", script], env=env, text=True,
                             capture_output=True, check=True)
        return run.stdout.split("RESULT=", 1)[1]

    def test_panvk_restores_shallow_queue_after_g720_frame_stutter(self):
        self.assertEqual(self.profile("/private/libvulkan_panfrost.so"),
                         "1:1:2:1:0:0")

    def test_manual_warmup_opt_out_remains_supported(self):
        # A known crash-prone cache can still disable preloading explicitly.
        source = RUNNER.read_text()
        self.assertIn("GOW3_BACKGROUND_WARMUP=${GOW3_BACKGROUND_WARMUP:-1}", source)
        presenter = (ROOT /
            "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text()
        self.assertIn("*background_warmup == '0'", presenter)

    def test_other_drivers_keep_existing_settings(self):
        for lib in ("/private/libvulkan_freedreno.so", "/system/libvulkan.so"):
            with self.subTest(lib=lib):
                self.assertEqual(self.profile(lib), "unset:unset:unset:unset:unset:unset")

    def test_opt_out_is_available(self):
        self.assertEqual(self.profile("/private/libvulkan_panfrost.so", "0"),
                         "unset:unset:unset:unset:unset:unset")

    def test_mali_shader_first_use_does_not_discard_graphics_draws(self):
        cache = (
            ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp"
        ).read_text()
        header = (
            ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.h"
        ).read_text()
        rasterizer = (
            ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
        ).read_text()
        self.assertIn("bool mali_sync_draws = false;", header)
        self.assertIn("vendorID == 0x13B5", cache)
        self.assertIn('std::getenv("GOW3_ANDROID_PORT")', cache)
        self.assertIn('std::getenv("GOW3_MALI_COMPLETE_DRAWS")', cache)
        self.assertIn("(!mali_sync_draws || mali_async_draw_wait) && compiler &&", cache)
        self.assertIn("GOW3_MALI_ASYNC_DRAW_WAIT", cache)
        self.assertIn("PublishShaders(true);", cache)
        self.assertIn("PublishGraphics(true);", cache)
        self.assertIn("if (ready != graphics_pipelines.end()) return ready->second.get();", cache)
        self.assertIn("if (!pipeline) {", rasterizer)
        self.assertIn("event=draw_skipped", rasterizer)
        self.assertIn("++g_gow3_pending_draws", cache)

    def test_scheduler_has_bounded_queue_setting(self):
        source = SCHEDULER.read_text()
        self.assertIn('std::getenv("GOW3_VK_MAX_IN_FLIGHT")', source)
        self.assertIn("requested >= 1 && requested <= 8", source)
        self.assertIn("work_semaphore.Wait(signal_value - MaxAndroidInFlightSubmissions)", source)


if __name__ == "__main__":
    unittest.main()
