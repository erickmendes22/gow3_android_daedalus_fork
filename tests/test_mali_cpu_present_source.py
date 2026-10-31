"""Mali PanVK CPU presentation isolation and source-contract checks.
This is a host-side preflight; only the native CI job compiles GPU code.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRESENTER = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text()
SWAPCHAIN = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_swapchain_ahb.cpp").read_text()
LAUNCHER = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()


class MaliCpuPresentContract(unittest.TestCase):
    def test_panvk_only_default_not_adreno(self):
        self.assertIn("*/libvulkan_panfrost.so)", LAUNCHER)
        self.assertIn('export GOW3_MALI_CPU_PRESENT=${GOW3_MALI_CPU_PRESENT:-1}', LAUNCHER)
        self.assertIn('if (swapchain.UsesCpuPresentation())', PRESENTER)
        self.assertIn('const vk::Image swapchain_image = swapchain.Image();', PRESENTER)

    def test_cpu_writable_linear_ahb_and_fence_retirement(self):
        self.assertIn("AHARDWAREBUFFER_USAGE_CPU_WRITE_OFTEN", SWAPCHAIN)
        self.assertIn("AHardwareBuffer_lock(", SWAPCHAIN)
        self.assertIn("AHardwareBuffer_unlock(", SWAPCHAIN)
        self.assertIn("while (!WaitSyncFile(fd, 1000))", SWAPCHAIN)
        self.assertIn("client.SendFrame(generation, image_index, frame_counter, width, height, -1)", SWAPCHAIN)
        self.assertIn("if (cpu_present) return;", SWAPCHAIN)

    def test_raw_rgba8_gpu_readback_and_frame_diagnostic(self):
        self.assertIn("cmdbuf.copyImageToBuffer(frame->image", PRESENTER)
        self.assertIn("vmaInvalidateAllocation(", PRESENTER)
        self.assertIn("instance.GetDevice().waitIdle()", PRESENTER)
        self.assertIn("MALI_CPU_PRESENT_SOURCE frame=", PRESENTER)
        self.assertIn("swapchain.PresentCpuPixels(pixels, frame->width, frame->height)", PRESENTER)

    def test_frame_generation_disabled_on_cpu_fallback(self):
        self.assertIn('? nullptr : Lsfg::Create(instance, lsfg_requested)', PRESENTER)


if __name__ == "__main__":
    unittest.main()
