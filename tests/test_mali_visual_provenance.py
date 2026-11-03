"""Check Mali visual trace covers image -> view -> draw -> VideoOut -> CPU -> gralloc."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
def source(relative):
    return (ROOT / relative).read_text()

IMG = source("gpu/shadps4/video_core/texture_cache/image.cpp")
VIEW = source("gpu/shadps4/video_core/texture_cache/image_view.cpp")
RAST = source("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
PRES = source("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
FRAME = source("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.h")
SWAP = source("gpu/shadps4/video_core/renderer_vulkan/vk_swapchain_ahb.cpp")
SWAPH = source("gpu/shadps4/video_core/renderer_vulkan/vk_swapchain_ahb.h")
APP = source("tools/android/bionic/present/gow3present.c")
NATIVE = source("tools/android/bionic/build_runtime.sh")
TRACE = source("gpu/shadps4/video_core/renderer_vulkan/vk_mali_visual_trace.h")
SH = source("tools/android/bionic/run-bionic.sh")
ARCHIVE = source("android-launcher/app/src/main/java/com/gow3/android/data/LogArchive.kt")

class MaliVisualProvenance(unittest.TestCase):
    def test_bounded_opt_out_and_arm_only(self):
        self.assertIn("GOW3_MALI_VISUAL_TRACE", TRACE)
        self.assertIn("vendor_id == 0x13B5", TRACE)
        self.assertIn("occurrence <= 16", TRACE)
        self.assertIn("(occurrence & (occurrence - 1)) == 0", TRACE)
        self.assertIn("GOW3_MALI_VISUAL_TRACE:-1", SH)
        self.assertIn("GOW3_MALI_AUTOCAPTURE:-0", SH)
        self.assertIn("GOW3_MALI_CPU_SNAPSHOTS:-1", SH)
    def test_creates_images_then_views_with_persistent_uids(self):
        for token in ("event=image_create", "event=image_unsupported", "image_uid",
                      "info.guest_address", "image_ci.format"):
            self.assertIn(token, IMG)
        for token in ("event=view_create", "event=view_reject", "image.image_uid",
                      "backing_format", "view_range.baseMipLevel"):
            self.assertIn(token, VIEW)
        self.assertIn("Vulkan::MaliVisualTrace::", IMG)
        self.assertIn("Vulkan::MaliVisualTrace::", VIEW)
    def test_tracks_draw_and_sampled_bindings(self):
        for token in ("event=texture_bound", "event=invalid_sharp", "event=empty_sharp",
                      "event=null_view_binding", "event=draw_record", "event=draw_skipped",
                      "depth_uid", "color_uid", "stage.pgm_hash"):
            self.assertIn(token, RAST)
        self.assertIn("image_infos.emplace_back(VK_NULL_HANDLE, VK_NULL_HANDLE", RAST)
        self.assertIn("GOW3_MALI_VISUAL_SUMMARY", TRACE)
    def test_videoout_and_final_ahb_linked(self):
        self.assertIn("mali_trace_source_uid", FRAME)
        self.assertIn("mali_trace_guest_address", FRAME)
        self.assertIn("event=videoout_prepare", PRES)
        self.assertIn("ReportPresented(", PRES)
        self.assertIn("frame->mali_capture_frame", PRES)
        self.assertIn("bool Swapchain::PresentCpuPixels(", SWAP)
        self.assertIn("u32 capture_frame = 0", SWAPH)
        self.assertIn("event=ahb_pixels", SWAP)
        self.assertIn("event=ahb_send", SWAP)
        self.assertIn('stage=ahb frame=', SWAP)
        self.assertIn("SaveMaliAhbBmp", SWAP)
        self.assertIn("ahb_*.bmp", SH)
        self.assertIn("logs.walkTopDown().forEach", ARCHIVE)

    def test_surface_control_receipt_and_completion_in_exported_zip(self):
        self.assertIn("GOW3_MALI_PRESENT_TRACE=1", NATIVE)
        self.assertIn("GOW3_MALI_VISUAL_APP", APP)
        for event in ("frame_receive", "frame_drop", "frame_queued",
                      "surface_submit", "surface_complete"):
            self.assertIn(event, APP)
        self.assertIn("ctx->shown_frame = frame;", APP)
        self.assertIn("android-present.log", APP)
        self.assertIn("S.path", APP)

if __name__ == "__main__":
    unittest.main()
