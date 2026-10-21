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
            ".reset = (guest_display_mode_recording ? !guest_display_history_contiguous : reset) ||",
            "!temporal_ready,",
            "cmdbuf.clearColorImage(vk::Image(motion_image)",
            "GSR2_HISTORY_GUARD dispatch=",
            "camera_motion.Gsr2HistoryValidity() == CameraMotion::Gsr2HistoryStatus::Valid",
        ):
            self.assertIn(expression, upscaler)


if __name__ == "__main__":
    unittest.main()
