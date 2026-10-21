"""GSR2 history boundary follows VideoOut flips, not arbitrary display draws."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "gpu/shadps4/video_core/renderer_vulkan"

class Gsr2VideoOutFrameBoundary(unittest.TestCase):
    def test_no_false_display_draw_boundaries_on_scaled_gsr2(self):
        raster = (ROOT/"vk_rasterizer.cpp").read_text()
        draw = raster.split("void Rasterizer::DrawRecord(", 1)[1].split(
            "void Rasterizer::", 1)[0]
        self.assertIn("const bool defer_gsr2_boundary_to_flip =", draw)
        self.assertIn('std::getenv("GOW3_GSR2_DIRECT_VIDEOOUT")', draw)
        self.assertIn("Gow3Settings::RenderPreset() != Gow3Settings::NativeAA", draw)
        self.assertIn("!defer_gsr2_boundary_to_flip && (!gsr2_bionic || scene_started)", draw)
        self.assertIn("camera_motion->OnDisplayPass(cb_descs[0].first)", draw)
        self.assertIn("upscaler->OnDisplayBoundary(cb_descs[0].first)", draw)

    def test_flip_drains_pending_draws_then_freezes_real_camera_depth(self):
        raster = (ROOT/"vk_rasterizer.cpp").read_text()
        header = (ROOT/"vk_rasterizer.h").read_text()
        present = (ROOT/"vk_presenter.cpp").read_text()
        self.assertIn("void Gsr2OnVideoOutFlip(VAddr guest_address);", header)
        body = raster.split("void Rasterizer::Gsr2OnVideoOutFlip(", 1)[1].split(
            "void Rasterizer::NoteFrameStart(", 1)[0]
        self.assertLess(body.index("DrainDrawPipe();"),
                        body.index("camera_motion->OnDisplayPass({});"))
        self.assertLess(body.index("camera_motion->OnDisplayPass({});"),
                        body.index("upscaler->OnFrameStart()"))
        self.assertIn("GSR2_VIDEOOUT_BOUNDARY", body)
        self.assertIn("scene_started = false;", body)
        self.assertIn('std::getenv("GOW3_ANDROID_PORT")', body)
        self.assertIn('std::getenv("GOW3_GSR2_DIRECT_VIDEOOUT")', body)
        self.assertIn('std::strcmp(selected, "gsr2") != 0', body)
        self.assertIn("Gow3Settings::RenderPreset() == Gow3Settings::NativeAA", body)
        flip = present.split("Frame* Presenter::PrepareFrame(",1)[1].split(
            "Frame* frame = GetRenderFrame();",1)[0]
        self.assertLess(flip.index("Gsr2OnVideoOutFlip(cpu_address)"),
                        flip.index("PresentGsr2FromGuestDisplay(image_id, display)"))

    def test_snapshot_is_captured_before_clearing_live_state(self):
        camera = (ROOT/"vk_camera_motion.cpp").read_text()
        snapshot = camera.split("void CameraMotion::OnDisplayPass(",1)[1].split(
            "void CameraMotion::Overlay(",1)[0]
        self.assertLess(snapshot.index("completed_history_status ="),
                        snapshot.index("current.valid = false;"))
        self.assertLess(snapshot.index("completed_depth = depth_id;"),
                        snapshot.index("depth_id = {};"))

if __name__ == "__main__":
    unittest.main()
