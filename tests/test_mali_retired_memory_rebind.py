"""Mali BC/RGBA128: rebind allocation only after Vulkan requirements match.

This covers an actual GPU memory allocation hot path, not driver/FPS claims.
The host test compiles the same C++ eligibility function used by image.cpp.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
IMAGE = (ROOT / "gpu/shadps4/video_core/texture_cache/image.cpp").read_text()
RUN = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()

class MemoryRebindPolicy(unittest.TestCase):
    def test_native_exact_policy_positive_and_negative_controls(self):
        compiler = shutil.which("c++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("Host compiler not available")
        code = r"""
#include "gpu/shadps4/video_core/texture_cache/retired_image_rebind_policy.h"
using VideoCore::CanRebindRetiredImageMemory;
// Rebind fresh BC3/RGBA128 VkImage to completed 8MiB VMA suballocation.
static_assert(CanRebindRetiredImageMemory(8*1024*1024, 65536, 0x02, false,
    8*1024*1024, 0, 1, false));
// At most 25% surplus allocation size is acceptable.
static_assert(CanRebindRetiredImageMemory(8*1024*1024, 65536, 0x02, false,
    9*1024*1024, 0, 1, false));
static_assert(!CanRebindRetiredImageMemory(8*1024*1024, 65536, 0x02, false,
    12*1024*1024, 0, 1, false));
// Dedicated VMA allocation can be bound only to its original VkImage.
static_assert(!CanRebindRetiredImageMemory(8*1024*1024, 65536, 0x02, false,
    8*1024*1024, 0, 1, true));
static_assert(!CanRebindRetiredImageMemory(8*1024*1024, 65536, 0x02, true,
    8*1024*1024, 0, 1, false));
// VK memory requirements must match actual type, offset and size.
static_assert(!CanRebindRetiredImageMemory(8*1024*1024, 65536, 0x04, false,
    8*1024*1024, 0, 1, false));
static_assert(!CanRebindRetiredImageMemory(8*1024*1024, 65536, 0x02, false,
    8*1024*1024, 4096, 1, false));
static_assert(!CanRebindRetiredImageMemory(8*1024*1024, 65536, 0x02, false,
    4*1024*1024, 0, 1, false));
static_assert(!CanRebindRetiredImageMemory(0, 65536, 0x02, false, 8*1024*1024, 0, 1, false));
static_assert(!CanRebindRetiredImageMemory(8*1024*1024, 0, 0x02, false,
    8*1024*1024, 0, 1, false));
static_assert(!CanRebindRetiredImageMemory(8*1024*1024, 65536, 0xffffffff, false,
    8*1024*1024, 0, 32, false));
int main() { return 0; }
"""
        with tempfile.TemporaryDirectory() as tmp:
            exe = str(Path(tmp) / "rebinding_guard")
            subprocess.run([compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT), "-x", "c++", "-", "-o", exe],
                           input=code, text=True, check=True)
            subprocess.run([exe], check=True)

    def test_retired_vkimage_never_reused_on_different_create(self):
        self.assertIn("const auto create_result = device.createImage(requested_ci);", IMAGE)
        self.assertIn("vmaGetAllocationInfo2(allocator, candidate.allocation, &info);", IMAGE)
        self.assertIn("dedicated.requiresDedicatedAllocation", IMAGE)
        self.assertIn("CanRebindRetiredImageMemory(", IMAGE)
        self.assertIn("info.allocationInfo.memoryType, info.dedicatedMemory", IMAGE)
        old_destroy = IMAGE.index("device.destroyImage(vk::Image{retired.image});")
        new_bind = IMAGE.index("vmaBindImageMemory(allocator, retired.allocation, new_handle)")
        self.assertLess(old_destroy, new_bind)
        self.assertIn("device.destroyImage(new_image);", IMAGE)
        self.assertIn("vmaFreeMemory(allocator, retired.allocation);", IMAGE)
        self.assertIn("return false;", IMAGE)
        self.assertIn("reused_from_pool = true;", IMAGE)
        self.assertIn("vmaCreateImage(allocator, &image_ci_unsafe", IMAGE)

    def test_opt_in_only_and_default_old_path(self):
        self.assertIn("GOW3_MALI_REBIND_RETIRED_MEMORY", IMAGE)
        self.assertIn("GOW3_MALI_REBIND_RETIRED_MEMORY=${GOW3_MALI_REBIND_RETIRED_MEMORY:-0}", RUN)
        self.assertIn("memory_rebind=$GOW3_MALI_REBIND_RETIRED_MEMORY", RUN)
        self.assertIn("if (recycle_bc && RebindRetiredImageMemory(", IMAGE)
        self.assertIn("if (recycle_bc && TakeBcImage(", IMAGE)

if __name__ == "__main__":
    unittest.main()
