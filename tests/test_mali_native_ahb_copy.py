"""Mali AHB overhead improvements: verified native output + fused RGBA alpha."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()
AHB = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_swapchain_ahb.cpp").read_text()
PRESENT = (ROOT / "tools/android/bionic/present/gow3present.c").read_text()


class MaliAhbPerformanceTests(unittest.TestCase):
    def test_verified_guest_resolution_only_and_rollback(self):
        self.assertIn('GOW3_MALI_NATIVE_AHB=${GOW3_MALI_NATIVE_AHB:-1}', SCRIPT)
        self.assertIn('"$GOW3_MALI_NATIVE_AHB" = 1', SCRIPT)
        self.assertIn('GOW3_RESOLUTION_STATUS:-}" = verified-direct-game-patch', SCRIPT)
        for resolution in ('960x540', '854x480', '752x424', '640x360', '426x240'):
            self.assertIn(resolution, SCRIPT)
        self.assertIn('GOW3_SCREEN_W="${GOW3_PATCH_INPUT_RES%x*}"', SCRIPT)
        self.assertIn('GOW3_SCREEN_H="${GOW3_PATCH_INPUT_RES#*x}"', SCRIPT)
        self.assertIn('GOW3_MALI_NATIVE_AHB=0', SCRIPT)
        self.assertIn('api.set_geometry(t, S.sc, &src, &dst, 0)', PRESENT)

    def test_four_buffers_with_rollback_and_no_vsync_change(self):
        self.assertIn('GOW3_PRESENT_BUFFERS=${GOW3_PRESENT_BUFFERS:-4}', SCRIPT)
        self.assertIn('GOW3_PRESENT_BUFFERS=3 restores', SCRIPT)
        mali = SCRIPT[SCRIPT.index('# Mali PanVK safe profile.'):]
        self.assertNotIn('export GOW3_VSYNC=0', mali)

    def test_opaque_neon_copy_and_original_path(self):
        self.assertIn('GOW3_MALI_AHB_FAST_COPY=${GOW3_MALI_AHB_FAST_COPY:-1}', SCRIPT)
        self.assertIn('void CopyOpaqueRgbaRow(u8* dst, const u8* src, u32 pixels)', AHB)
        self.assertIn('vorrq_u8(colors, opaque_alpha)', AHB)
        self.assertIn('u32 rgba;', AHB)
        self.assertIn('rgba |= 0xff000000u;', AHB)
        self.assertIn('CopyOpaqueRgbaRow(row, input_row, fit_w)', AHB)
        self.assertIn("std::memcpy(row, input_row, size_t(fit_w) * 4);", AHB)
        self.assertIn('src_y == previous_src_y', AHB)
        self.assertIn('std::memcpy(row, previous_output_row, size_t(fit_w) * 4)', AHB)
        self.assertIn('if (fit_w != dst_w || fit_h != dst_h)', AHB)

    def test_no_change_to_working_cpu_presentation(self):
        self.assertIn('AHardwareBuffer_lock(', AHB)
        self.assertIn('AHardwareBuffer_unlock(', AHB)
        self.assertIn('client.SendFrame(', AHB)
        self.assertIn('AHARDWAREBUFFER_USAGE_CPU_WRITE_OFTEN', AHB)


if __name__ == "__main__":
    unittest.main()
