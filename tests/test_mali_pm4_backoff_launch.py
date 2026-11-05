"""Safety gates for the Mali-only experimental PM4 backoff tester package."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class BackoffLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()
        cls.gpu=(ROOT/"gpu/shadps4/video_core/amdgpu/liverpool.cpp").read_text()

    def test_opted_in_only_in_panfrost_launcher_case(self):
        case=self.launcher.index('case "\${GOW3_VULKAN_DRIVER:-}" in')
        driver=self.launcher.index('  */libvulkan_panfrost.so)',case)
        backoff=self.launcher.index('export GOW3_MALI_PM4_IDLE_BACKOFF_US=',driver)
        end=self.launcher.index('# End Mali PanVK safe profile.',backoff)
        self.assertLess(driver,backoff)
        self.assertLess(backoff,end)
        self.assertIn('GOW3_MALI_PM4_IDLE_BACKOFF_US:-20',self.launcher)
        self.assertIn('pm4_idle_us=$GOW3_MALI_PM4_IDLE_BACKOFF_US',self.launcher)

    def test_gpu_requires_mali_custom_driver_and_blocked_yield(self):
        for item in ('std::strstr(driver, "panfrost")','GOW3_ANDROID_PORT',
                     'gfx_blocked_fiber_wait',
                     'num_submits.load(std::memory_order_relaxed) == 1',
                     'num_commands.load(std::memory_order_relaxed) == 0',
                     'us >= 1 && us <= 100',
                     'std::this_thread::sleep_for(std::chrono::microseconds(idle_backoff_us))'):
            with self.subTest(item=item):
                self.assertIn(item,self.gpu)
        self.assertIn("return us >= 1 && us <= 100 ? unsigned(us) : 0u;",self.gpu)

    def test_existing_sync_improvements_remain_opt_in(self):
        sem=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_semaphore.cpp").read_text()
        pool=(ROOT/"gpu/shim/gow3_copy.cpp").read_text()
        self.assertIn('GOW3_MALI_DIRECT_TIMELINE_WAIT',sem)
        self.assertIn("(opt && opt[0] == '1')",sem)
        self.assertIn('GOW3_MALI_COPY_EPOCH_WAIT',pool)
        self.assertIn("opt && opt[0] == '1'",pool)

if __name__=="__main__":
    unittest.main()
