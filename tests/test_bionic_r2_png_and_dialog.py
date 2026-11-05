"""Regressions from real 2026-10-19 device logs: a valid per-save PNG
was located but FFmpeg failed, and controls never refreshed for the dialog.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding="utf-8")

class BionicR2Tests(unittest.TestCase):
    def test_png_decoder_does_not_flush_before_receiving_frame(self):
        png = read("gpu/shim/gow3_png.cpp")
        self.assertIn("avcodec_send_packet(context, packet)", png)
        self.assertIn("avcodec_receive_frame(context, frame)", png)
        self.assertNotIn("avcodec_send_packet(context, nullptr)", png)
        self.assertIn("Save PNG: FFmpeg send=", png)
        self.assertIn("Save PNG: decoder setup failed", png)
        self.assertIn("Save PNG: unsupported swscale", png)

    def test_ongoing_touch_refresh_observes_native_dialog_marker(self):
        code = read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/TouchControllerOverlay.java")
        self.assertIn("postInvalidateDelayed(200)", code)
        self.assertIn("saveDialogFlag.isFile()", code)
        self.assertIn("if (!modal || editing)", code)
        # GoW3 uses the smaller, caption-only mobile action circles.
        # Cross and Circle must remain visible while the native save dialog is up.
        self.assertIn('gowAction(c,"cross","×",39)', code)
        self.assertIn('gowAction(c,"circle","○",33)', code)

    def test_only_first_bloodframe_present_is_diagnosed(self):
        code = read("gpu/shadps4/video_core/renderer_vulkan/gow3_lsfg.cpp")
        self.assertIn("const bool trace_first_frame = ctx.frame == 0;", code)
        for marker in ("context ready", "first GPU copy submit returned",
                       "pre-engine present", "first engine present completed"):
            self.assertIn("Bloodframe trace: " + marker, code)

if __name__ == "__main__":
    unittest.main()
