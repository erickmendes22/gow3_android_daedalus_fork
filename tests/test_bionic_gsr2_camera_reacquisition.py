"""Safeguard experimental GSR2 post-cutscene camera reacquisition."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CAMERA_CPP = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp"
CAMERA_H = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.h"
UPSCALER_CPP = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp"


class Gsr2CameraReacquisition(unittest.TestCase):
    def test_adjacent_camera_geometry_captured_from_gow3(self):
        cpp = r"""
#include <cmath>
#include <limits>
#include "gpu/shadps4/video_core/renderer_vulkan/gow3_camera_layout.h"
using namespace Gow3CameraLayout;

int main() {
    // Actual CUSA01623 shader 05756ef0a3a4414c, vertex slot 1,
    // two verified camera matrices captured in the 2026-10-19 session.
    const float before[32] = {
        1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1,
        -1.92641294f, -.0862333775f, .204205185f, .204203621f,
         .000354632095f, 3.47399640f, .120652519f, .120651595f,
         .404891312f, -.413328439f, .971472323f, .971464932f,
        87.0151062f,-962.621643f,264.712341f,265.210327f
    };
    const float after[32] = {
        1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1,
        -1.93218994f, -.085549064f, .203650191f, .203648642f,
        .000457424117f, 3.48428059f, .119944811f, .119943894f,
        .404904306f, -.41217351f, .971676469f, .971669078f,
        86.8912888f, -964.743835f, 264.933899f, 265.431885f
    };
    const auto a = RecoverViewProjection(before, 32, 1);
    auto b = RecoverViewProjection(after, 32, 1);
    if (!a.valid || !b.valid) return 1;
    if (!CompatibleAdjacentCameraSamples(a, b)) return 2;
    const auto original = b;
    b.position[0] += 12.0f;
    if (CompatibleAdjacentCameraSamples(a, b)) return 3;
    b = original;
    b.projection[1] += 0.3f;
    if (CompatibleAdjacentCameraSamples(a, b)) return 4;
    b = original;
    for (unsigned i = 8; i < 11; ++i) b.view[i] = -b.view[i];
    if (CompatibleAdjacentCameraSamples(a, b)) return 5;
    b = original;
    b.valid = false;
    if (CompatibleAdjacentCameraSamples(a, b)) return 6;
    b = original;
    b.position[1] = std::numeric_limits<float>::quiet_NaN();
    if (CompatibleAdjacentCameraSamples(a, b)) return 7;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "camera_test.cpp"
            binary = Path(temp) / "camera_test"
            source.write_text(cpp, encoding="utf-8")
            result = subprocess.run(
                ["c++", "-std=c++20", "-O2", "-Wall", "-Wextra",
                 "-I", str(ROOT), str(source), "-o", str(binary)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_verified_frame_continues_bounded_multisource_discovery(self):
        src = CAMERA_CPP.read_text(encoding="utf-8")
        header = CAMERA_H.read_text(encoding="utf-8")
        self.assertIn("u32 frame_extra_source_probes = 0;", header)
        scan = src.split("void CameraMotion::OnConstants(", 1)[1].split(
            "void CameraMotion::OnGBufferPass(", 1)[0]
        self.assertIn("frame_extra_source_probes >= 64", scan)
        self.assertIn("source.valid && source.shader_hash == shader_hash", scan)
        self.assertIn("++frame_extra_source_probes;", scan)
        self.assertLess(scan.index("++frame_extra_source_probes;"),
                        scan.index("Gow3CameraLayout::RecoverViewProjection("))
        self.assertIn("current.shader_hash == frame_camera_shader_hash", scan)
        boundary = src.split("void CameraMotion::OnDisplayPass(", 1)[1].split(
            "void CameraMotion::Overlay(", 1)[0]
        self.assertIn("GSR2_CAMERA_SOURCE_POOL", boundary)
        self.assertIn("frame_extra_source_probes = 0;", boundary)
        self.assertLess(boundary.index("previous_frame_sources = current_frame_sources;"),
                        boundary.index("frame_extra_source_probes = 0;"))

    def test_multiple_shader_candidates_survive_one_frame_only(self):
        # The 19:49 log saturated all 16 source slots on most gameplay frames.
        # The 12:39 log also recovered distinct camera shaders after autosave.
        # cinematic, but the single previous_frame_candidate slot discarded
        # some before an adjacent frame could confirm them.
        c = CAMERA_CPP.read_text(encoding="utf-8")
        h = CAMERA_H.read_text(encoding="utf-8")
        self.assertIn("static constexpr size_t MaxFrameCameraSources = 32;", h)
        # Increasing storage cannot relax the 64-probe CPU budget.
        self.assertIn("frame_extra_source_probes >= 64", source)
        self.assertIn("std::array<Camera, MaxFrameCameraSources> current_frame_sources{}", h)
        self.assertIn("std::array<Camera, MaxFrameCameraSources> previous_frame_sources{}", h)
        source = c.split("void CameraMotion::OnConstants(", 1)[1].split(
            "void CameraMotion::OnGBufferPass(", 1)[0]
        self.assertIn("candidate.shader_hash == shader_hash", source)
        self.assertIn("prior_source = &candidate;", source)
        self.assertIn("const bool same_source_last_frame = prior_source != nullptr;", source)
        self.assertIn("earlier.view = prior_source->view;", source)
        self.assertIn("CompatibleAdjacentCameraSamples(earlier, recovered)", source)
        self.assertIn("GSR2_CAMERA_MULTI_SOURCE_RECOVERED", source)
        self.assertIn("source_slot->valid = true;", source)
        boundary = c.split("void CameraMotion::OnDisplayPass(", 1)[1].split(
            "void CameraMotion::Overlay(", 1)[0]
        self.assertIn("previous_frame_sources = current_frame_sources;", boundary)
        self.assertIn("current_frame_sources = {};", boundary)
        self.assertLess(boundary.index("previous_frame_sources = current_frame_sources;"),
                        boundary.index("current_frame_sources = {};"))
        # Keep original single-slot source and real-geometry cut protection.
        self.assertIn("previous_frame_candidate.shader_hash == shader_hash", source)
        self.assertIn("!keep_verified_camera", source)

    def test_proven_shader_camera_cannot_be_downgraded_by_legacy_pair(self):
        # A GoW III RecoverViewProjection result bound to an actual shader
        # must not be replaced by a later UI/model FindPose candidate which
        # intentionally has shader_hash=0. That caused history loss after
        # the initially successful camera sequence in 426p/360p logs.
        src = CAMERA_CPP.read_text(encoding="utf-8")
        on_constants = src.split("void CameraMotion::OnConstants(", 1)[1].split(
            "void CameraMotion::OnGBufferPass(", 1)[0]
        exact = on_constants.index("Gow3CameraLayout::RecoverViewProjection(")
        guard = on_constants.index("const bool keep_verified_camera =")
        fallback = on_constants.index("if (have_pose && have_projection && frame_pose_votes >= 2 &&\n        !keep_verified_camera)")
        self.assertLess(exact, guard)
        self.assertLess(guard, fallback)
        self.assertIn("gow3_android_gsr2 && current.valid && current.shader_hash != 0", on_constants[guard:guard + 190])
        self.assertIn("GSR2_CAMERA_PROVENANCE_PROTECTED", on_constants)
        self.assertLess(fallback, on_constants.index("current.shader_hash = 0;", fallback))
        self.assertIn("current.shader_hash = frame_camera_shader_hash;", on_constants)

    def test_reacquisition_does_not_disable_temporal_protection(self):
        code = CAMERA_CPP.read_text(encoding="utf-8")
        header = CAMERA_H.read_text(encoding="utf-8")
        upscaler = UPSCALER_CPP.read_text(encoding="utf-8")
        # The old path reached 3 pose votes with no exact source hash,
        # then incorrectly returned before RecoverViewProjection().
        self.assertIn("(!gow3_android_gsr2 || current.shader_hash != 0)", code)
        self.assertLess(
            code.index("if (frame_has_camera && frame_pose_votes >= 3 &&"),
            code.index("Gow3CameraLayout::RecoverViewProjection("))
        # Two provenance clears: unverified affine fallback, frame boundary.
        self.assertGreaterEqual(code.count("current.shader_hash = 0;"), 2)
        fallback = code.index('std::printf("GOW3_CAMERA_VERIFIED pair=1')
        self.assertLess(code.rfind("current.shader_hash = 0;", 0, fallback), fallback)
        for expression in (
            "previous_frame_candidate.shader_hash == shader_hash",
            "CompatibleAdjacentCameraSamples(earlier, recovered)",
            "current_frame_candidate.valid = false;",
            "GSR2_CAMERA_REACQUIRED",
            "frame_pose_votes = 2;",
        ):
            self.assertIn(expression, code)
        for expression in (
            "current.shader_hash != previous.shader_hash",
            "Gsr2HistoryValidity() const noexcept",
        ):
            self.assertIn(expression, header)
        for expression in (
            "const bool dispatch_reset =",
            "(guest_display_mode_recording ? !guest_display_history_contiguous : reset) ||",
            "!temporal_ready;",
            ".reset = dispatch_reset,",
            "cmdbuf.clearColorImage(vk::Image(motion_image)",
            "GSR2_HISTORY_GUARD dispatch=",
            "camera_motion.Gsr2HistoryValidity() == CameraMotion::Gsr2HistoryStatus::Valid",
        ):
            self.assertIn(expression, upscaler)


if __name__ == "__main__":
    unittest.main()
