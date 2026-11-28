"""Static regression guards for Mali CPU-present resolution and fallback."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRES = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text()
SH = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()


class MaliPresentSourceResolution(unittest.TestCase):
    def test_opt_in_by_driver_and_rollback(self):
        self.assertIn("*/libvulkan_panfrost.so)", SH)
        self.assertIn("GOW3_MALI_PRESENT_REDUCE=${GOW3_MALI_PRESENT_REDUCE:-1}", SH)
        self.assertIn('std::getenv("GOW3_MALI_PRESENT_REDUCE")', PRES)
        self.assertIn("if (!reduce || reduce[0] != '0')", PRES)
        self.assertIn("if (swapchain.UsesCpuPresentation())", PRES)

    def test_resize_precedes_frame_acquisition_and_readback(self):
        first = PRES.index("Frame* Presenter::PrepareFrame(")
        acquire = PRES.index("Frame* frame = GetRenderFrame(true);", first)
        size = PRES.index("SetExpectedGameSize(s32(target_w), s32(target_h));", first)
        self.assertLess(size, acquire)
        self.assertIn("const vk::Extent2D output = swapchain.GetExtent()", PRES)
        self.assertIn("verified_patch.width <= output.width", PRES)
        self.assertIn("verified_patch.height <= output.height", PRES)
        self.assertIn("cmdbuf.copyImageToBuffer(readback_image,", PRES)
        self.assertIn("waitForFences(frame->present_done, true, ~0ull)", PRES)
        self.assertIn("swapchain.PresentCpuPixels(", PRES)

    def test_patch_only_when_verified_by_launch_env(self):
        self.assertIn('"GOW3_RESOLUTION_STATUS"', PRES)
        self.assertIn('"verified-direct-game-patch"', PRES)
        self.assertIn('"GOW3_PATCH_INPUT_RES"', PRES)
        self.assertIn('std::sscanf(input, "%ux%u%c"', PRES)
        self.assertIn("w >= 320 && h >= 180", PRES)

    def test_standard_480p_native_ahb_uses_verified_patch_only(self):
        # Execute just the launcher's AHB selection block in a host shell.
        # No Android dependencies or game executable are needed.
        import os
        import subprocess
        start = SH.index('      export GOW3_MALI_NATIVE_AHB=')
        end = SH.index('      # 4 buffers rather than 3', start)
        script = SH[start:end] + '\n' + 'printf "%sx%s" "$GOW3_SCREEN_W" "$GOW3_SCREEN_H"'
        base = {
            'GOW3_MALI_CPU_PRESENT': '1',
            'GOW3_MALI_NATIVE_AHB': '1',
            'GOW3_RESOLUTION_STATUS': 'native-game-patch',
            'GOW3_PATCH_STATUS': 'validated',
            'GOW3_GAME_VERSION': '01.02',
            'GOW3_EBOOT_SHA256': '6e72330e9092e5164049b865e5568f2d450904001a73fe0a2f4b39194c195b3c',
            'GOW3_PATCHES': 'Bug Fix - Startup Black Screen;Resolution Patch - 480p',
            'GOW3_SCREEN_W': '1280',
            'GOW3_SCREEN_H': '720',
        }
        cases = [
            ({}, '854x480'),
            ({'GOW3_MALI_NATIVE_AHB': '0'}, '1280x720'),
            ({'GOW3_MALI_CPU_PRESENT': '0'}, '1280x720'),
            ({'GOW3_PATCH_STATUS': 'unsupported-app-version'}, '1280x720'),
            ({'GOW3_GAME_VERSION': '01.00'}, '1280x720'),
            ({'GOW3_EBOOT_SHA256': 'wrong'}, '1280x720'),
            ({'GOW3_PATCHES': 'Resolution Patch - 720p'}, '1280x720'),
            ({'GOW3_RESOLUTION_STATUS': 'verified-direct-game-patch',
              'GOW3_PATCH_INPUT_RES': '752x424'}, '752x424'),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                actual = subprocess.check_output(
                    ['sh', '-eu', '-c', script],
                    env={**os.environ, **base, **changes}, text=True)
                self.assertEqual(actual, expected)

    def test_direct_patch_resolution_contract(self):
        launch = (ROOT / "scripts/launch_env.py").read_text()
        self.assertIn("updates['GOW3_PATCH_INPUT_RES']", launch)
        self.assertIn("updates['GOW3_RESOLUTION_STATUS'] = 'verified-direct-game-patch'", launch)


if __name__ == "__main__":
    unittest.main()
