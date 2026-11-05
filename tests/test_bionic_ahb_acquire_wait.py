"""Prevent a null AHB acquire semaphore from reaching Vulkan queue submission."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRESENTER = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp"


class BionicAhbAcquireWait(unittest.TestCase):
    def test_both_present_paths_use_filtered_wait(self):
        source = PRESENTER.read_text()
        self.assertIn('#include "video_core/renderer_vulkan/vk_ahb_acquire_wait.h"', source)
        loading = source.split("void Presenter::PresentLoadingFrame()", 1)[1].split(
            "void Presenter::Present(Frame*", 1
        )[0]
        normal = source.split("void Presenter::Present(Frame*", 1)[1].split(
            "Frame* Presenter::GetRenderFrame()", 1
        )[0]
        for path in (loading, normal):
            self.assertIn("AddImageAcquiredWait(info, swapchain.GetImageAcquiredSemaphore());", path)
            # No branch may add an unchecked null wait (including desktop paths).
            self.assertNotIn("info.AddWait(swapchain.GetImageAcquiredSemaphore());", path)

    @unittest.skipUnless(shutil.which("g++"), "g++ required")
    def test_first_use_cpu_fallback_and_imported_release_fence(self):
        program = r'''
#include <cassert>
#include "gpu/shadps4/video_core/renderer_vulkan/vk_ahb_acquire_wait.h"
struct Semaphore {
    int handle;
    explicit operator bool() const { return handle != 0; }
};
struct SubmitInfo {
    int num_wait_semas{};
    int last_wait_handle{};
    void AddWait(Semaphore s) {
        assert(s.handle != 0); // The original bug submits VK_NULL_HANDLE here.
        ++num_wait_semas;
        last_wait_handle = s.handle;
    }
};
int main() {
    SubmitInfo loading{};
    Vulkan::AddImageAcquiredWait(loading, Semaphore{0}); // New AHB, no release fence.
    assert(loading.num_wait_semas == 0);
    SubmitInfo normal{};
    Vulkan::AddImageAcquiredWait(normal, Semaphore{0}); // CPU already waited release fence.
    assert(normal.num_wait_semas == 0);
    Vulkan::AddImageAcquiredWait(normal, Semaphore{123}); // Imported release fence.
    assert(normal.num_wait_semas == 1 && normal.last_wait_handle == 123);
    Vulkan::AddImageAcquiredWait(normal, Semaphore{0}); // No stale wait on reuse.
    assert(normal.num_wait_semas == 1);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.cpp"
            binary = Path(directory) / "test"
            source.write_text(program)
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT), str(source), "-o", str(binary)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
