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
                        body.index("camera_motion->OnDisplayPass({}, guest_address);"))
        self.assertLess(body.index("camera_motion->OnDisplayPass({}, guest_address);"),
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

    def test_temporal_history_consumes_exact_display_flip_and_generation(self):
        header = (ROOT/"vk_camera_motion.h").read_text()
        cam = (ROOT/"vk_camera_motion.cpp").read_text()
        up = (ROOT/"vk_temporal_upscaler.cpp").read_text()
        up_h = (ROOT/"vk_temporal_upscaler.h").read_text()
        self.assertIn("CompletedVideoOutAddress() const noexcept", header)
        self.assertIn("CompletedVideoOutGeneration() const noexcept", header)
        self.assertIn("++completed_videoout_generation;", cam)
        self.assertIn("guest_display_last_flip_generation = 0;", up_h)
        func = up.split("bool TemporalUpscaler::PresentGsr2FromGuestDisplay(",1)[1].split(
            "bool TemporalUpscaler::DisplayOverride(",1)[0]
        for required in (
            "CompletedVideoOutGeneration()",
            "CompletedVideoOutAddress() == source.info.guest_address",
            "flip_generation != guest_display_last_flip_generation",
            "flip_generation == guest_display_last_flip_generation + 1",
            "if (!source_matches_flip || !adjacent_flip)",
            "guest_display_history_contiguous = false;",
            "guest_display_last_flip_generation = flip_generation;",
            "GSR2_VIDEOOUT_MOTION",
            "matched=%d adjacent=%d",
        ):
            self.assertIn(required, func)
        self.assertLess(func.index("guest_display_last_flip_generation = flip_generation;"),
                        func.index("GSR2_VIDEOOUT_MOTION"))

    def test_motion_direction_and_units_match_gsr2_history_uv(self):
        # GoW3 camera_motion: previous_uv - current_uv in render pixels.
        # GSR2 convert: negate and scale by 2/renderSize into clip units.
        # GSR2 upscale: PrevUV = currentUV - .5 * converted_clip.
        camera_glsl=(ROOT.parent/"host_shaders"/"camera_motion.comp").read_text()
        convert=(ROOT.parent/"host_shaders"/"gsr2_convert.comp").read_text()
        upscale=(ROOT.parent/"host_shaders"/"gsr2_upscale.comp").read_text()
        self.assertIn("const vec2 motion = (prev_uv - scene_uv) * size;",camera_glsl)
        self.assertIn("vec2 motionPixels = texelFetch(InputMotion, InputPos, 0).xy;",convert)
        self.assertIn("vec2 motion = -motionPixels * 2.0 * params.renderSizeRcp;",convert)
        self.assertIn("depthclip=1.0;",convert)
        self.assertIn("vec2 rawPrevUV = -0.5 * Motion + Hruv;",upscale)
        self.assertIn("vec2 PrevUV = clamp(rawPrevUV",upscale)
        self.assertIn("if (invalidReprojection) alpha=1.0;",upscale)
        for w,h in ((426,240),(640,360),(752,424),(960,540)):
            for current,previous in (((.5,.5),(.501,.503)),
                                     ((.21,.78),(.209,.781)),
                                     ((.87,.09),(.868,.091))):
                motion=((previous[0]-current[0])*w,
                        (previous[1]-current[1])*h)
                converted=(-2*motion[0]/w,-2*motion[1]/h)
                recovered=(current[0]-.5*converted[0],
                           current[1]-.5*converted[1])
                self.assertAlmostEqual(recovered[0],previous[0],places=6)
                self.assertAlmostEqual(recovered[1],previous[1],places=6)

    def test_provenance_is_taken_from_real_display_draw_not_assigned_at_flip(self):
        h = (ROOT/"vk_camera_motion.h").read_text()
        camera = (ROOT/"vk_camera_motion.cpp").read_text()
        raster = (ROOT/"vk_rasterizer.cpp").read_text()
        self.assertIn("void OnDisplayTargetDraw(VAddr guest_address);", h)
        self.assertIn("struct DisplayTargetCandidate", h)
        self.assertIn("std::array<DisplayTargetCandidate, MaxDisplayTargetCandidates> display_target_candidates{}", h)
        draw = raster.split("void Rasterizer::DrawRecord(",1)[1].split(
            "void Rasterizer::",1)[0]
        self.assertIn("is_display_draw && scene_started", draw)
        self.assertIn("camera_motion->OnDisplayTargetDraw(regs.color_buffers[0].Address());",draw)
        capture = camera.split("void CameraMotion::OnDisplayTargetDraw(",1)[1].split(
            "void CameraMotion::OnDisplayPass(",1)[0]
        self.assertIn("candidate.address = guest_address;", capture)
        self.assertIn("candidate.camera = current;",capture)
        self.assertIn("candidate.depth = depth_id;",capture)
        self.assertIn("candidate.depth_image_uid = depth_image.image_uid;",capture)
        self.assertIn("candidate.depth_alias_generation = depth_image.alias_generation;",capture)
        self.assertIn("!current.shader_hash || !depth_id",capture)
        self.assertIn("if (candidate.address == guest_address)",capture)
        flip = camera.split("void CameraMotion::OnDisplayPass(",1)[1].split(
            "void CameraMotion::Overlay(",1)[0]
        self.assertIn("candidate.address != presented_guest_address",flip)
        self.assertIn("current = candidate.camera;",flip)
        self.assertIn("depth_id = candidate.depth;",flip)
        self.assertIn("texture_cache.TryGetImage(candidate.depth, candidate.depth_image_uid)",flip)
        self.assertIn("depth_image->alias_generation != candidate.depth_alias_generation",flip)
        self.assertLess(
            flip.index("texture_cache.TryGetImage(candidate.depth, candidate.depth_image_uid)"),
            flip.index("current = candidate.camera;"))
        self.assertIn("current.valid = false;",flip)
        self.assertIn("depth_id = {};",flip)
        self.assertIn("display_target_candidates = {};",flip)
        self.assertIn("GSR2_FRAMEBUFFER_SCENE_MATCH",flip)
        # The matching camera must be installed BEFORE calculating history.
        self.assertLess(flip.index("current = candidate.camera;"),
                        flip.index("completed_history_status ="))

    def test_snapshot_is_captured_before_clearing_live_state(self):
        camera = (ROOT/"vk_camera_motion.cpp").read_text()
        snapshot = camera.split("void CameraMotion::OnDisplayPass(",1)[1].split(
            "void CameraMotion::Overlay(",1)[0]
        history = snapshot.index("completed_history_status =")
        depth = snapshot.index("completed_depth = depth_id;")
        self.assertLess(history, snapshot.index("current.valid = false;", history))
        self.assertLess(depth, snapshot.index("depth_id = {};", depth))

if __name__ == "__main__":
    unittest.main()
