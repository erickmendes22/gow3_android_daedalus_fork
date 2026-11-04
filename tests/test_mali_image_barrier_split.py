"""Exercises real C++ image/buffer barrier policy and preserves the Vulkan hazard gates."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
R = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_runtime.cpp").read_text()
H = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_runtime.h").read_text()
GPU = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
RUN = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()

class BarrierSplitTests(unittest.TestCase):
    def test_cplusplus_policy_matrix(self):
        compiler = shutil.which("c++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("host C++ compiler not installed")
        source = r"""
            #include "gpu/shadps4/video_core/renderer_vulkan/vk_barrier_flush_policy.h"
            using namespace Vulkan;
            static_assert(DecideBarrierFlush(false, false, false, true, true).emit_memory);
            static_assert(DecideBarrierFlush(true, false, false, true, true).emit_images);
            static_assert(!DecideBarrierFlush(true, false, false, true, true).emit_memory);
            static_assert(!DecideBarrierFlush(true, false, false, true, true).retire_buffer_ranges);
            static_assert(DecideBarrierFlush(true, true, false, true, false).emit_memory);
            static_assert(DecideBarrierFlush(true, true, false, true, false).retire_buffer_ranges);
            static_assert(DecideBarrierFlush(true, false, true, true, false).emit_memory);
            static_assert(DecideBarrierFlush(true, false, true, true, false).retire_buffer_ranges);
            static_assert(!DecideBarrierFlush(true, false, false, false, false).has_work());
            static_assert(DecideBarrierFlush(true, false, false, false, true).emit_images);
            int main() {}
        """
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "barrier_policy"
            subprocess.run([compiler, "-std=c++20", "-Werror", "-Wall", "-Wextra",
                            "-I", str(ROOT), "-x", "c++", "-", "-o", str(output)],
                           input=source, text=True, check=True)
            subprocess.run([str(output)], check=True)

    def test_gpu_dependency_safety(self):
        self.assertIn("buffer_hazard_pending |= has_access;", R)
        self.assertIn("if (check_read_access && !has_access)", R)
        self.assertIn("barrier_tracker.FindRange(range, Access::Read)", R)
        self.assertIn("barrier_tracker.FindRange(range, Access::Write)", R)
        self.assertIn("if (decision.retire_buffer_ranges) {", R)
        self.assertIn("barrier_tracker.Clear();", R)
        self.assertIn("buffer_hazard_pending = false;", R)
        self.assertIn("++access_epoch;", R)
        self.assertIn("runtime.FlushBarriers(true);", GPU)
        self.assertIn("FlushBarriers(bool force_buffer_barrier = false)", H)

    def test_mali_only_and_rollback(self):
        self.assertIn("vendorID == 0x13B5", R)
        self.assertIn("GOW3_MALI_IMAGE_BARRIER_SPLIT", R)
        self.assertIn("GOW3_MALI_IMAGE_BARRIER_SPLIT=${GOW3_MALI_IMAGE_BARRIER_SPLIT:-1}", RUN)

if __name__ == "__main__":
    unittest.main()
