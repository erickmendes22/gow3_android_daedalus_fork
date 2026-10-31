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

    def test_panvk_is_conservative(self):
        self.assertEqual(self.profile("/private/libvulkan_panfrost.so"),
                         "1:0:2:1:0:0")

    def test_other_drivers_keep_existing_settings(self):
        for lib in ("/private/libvulkan_freedreno.so", "/system/libvulkan.so"):
            with self.subTest(lib=lib):
                self.assertEqual(self.profile(lib), "unset:unset:unset:unset:unset:unset")

    def test_opt_out_is_available(self):
        self.assertEqual(self.profile("/private/libvulkan_panfrost.so", "0"),
                         "unset:unset:unset:unset:unset:unset")

    def test_scheduler_has_bounded_queue_setting(self):
        source = SCHEDULER.read_text()
        self.assertIn('std::getenv("GOW3_VK_MAX_IN_FLIGHT")', source)
        self.assertIn("requested >= 1 && requested <= 8", source)
        self.assertIn("work_semaphore.Wait(signal_value - MaxAndroidInFlightSubmissions)", source)


if __name__ == "__main__":
    unittest.main()
