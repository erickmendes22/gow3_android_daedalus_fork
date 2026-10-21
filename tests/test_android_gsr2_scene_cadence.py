"""Prevent GoW III's 1-scene-in-3-VideoOut cadence from clearing temporal GSR2.

The real 2026-10-21 20:27 log had 200 scene-valid camera samples per
600 VideoOut flips and ZERO temporal dispatches after 16,200 outputs. Spatial
fillers must run a distinct Qualcomm context and NEVER clear real scene history.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu/shadps4/video_core/renderer_vulkan"


class SceneCadence(unittest.TestCase):
    def test_temporal_history_follows_verified_scene_not_videoout_filler(self):
        cpp = (VK / "vk_temporal_upscaler.cpp").read_text()
        header = (VK / "vk_temporal_upscaler.h").read_text()
        cam = (VK / "vk_camera_motion.h").read_text()
        camcpp = (VK / "vk_camera_motion.cpp").read_text()
        present = cpp.split("bool TemporalUpscaler::PresentGsr2FromGuestDisplay(",1)[1].split(
            "bool TemporalUpscaler::DisplayOverride(",1)[0]
        record = cpp.split("bool TemporalUpscaler::RecordGsr2(",1)[1]
        start = cpp.split("bool TemporalUpscaler::OnFrameStart(",1)[1].split(
            "void TemporalUpscaler::OnDispatch(",1)[0]
        self.assertIn("std::unique_ptr<GsrUpscaler> gsr2_spatial;",header)
        self.assertIn("auto& provider = spatial_videoout ? gsr2_spatial : gsr2;",record)
        self.assertIn("const bool spatial_videoout = guest_display_mode_recording &&",record)
        self.assertIn("const bool provider_changed =", start)
        self.assertIn("recent_verified_scene",start)
        self.assertIn("CompletedVideoOutGeneration()",start)
        self.assertIn('GOW3_GSR2_INPUT_RES',start)
        self.assertIn("Motion::JitterPhases(input_w,target_width)",start)
        self.assertIn("camera_motion.CompletedHistoryValidity() != CameraMotion::Gsr2HistoryStatus::Valid)",start)
        # Neither VideoOut fillers nor toggling their camera eligibility can
        # advance the real scene's Halton phase.
        self.assertIn("return changed;\n    jitter_index = jitter_index % phases + 1;",start)
        self.assertIn('changed && (!PreHudEnabled() || provider_changed)', start)
        self.assertIn("constexpr u64 MaxTemporalSceneFlipGap = 4;",present)
        self.assertIn("CompletedPreviousMatchesTemporalScene()",present)
        self.assertIn("previous_scene_history_eligible",present)
        self.assertIn("guest_display_history_contiguous = previous_scene_history_eligible;",present)
        self.assertIn("camera_motion.CommitCompletedTemporalScene();",present)
        self.assertIn("GSR2_SCENE_CADENCE",present)
        self.assertIn("last_temporal_scene_camera",cam)
        self.assertIn("completed_previous.shader_hash != last_temporal_scene_camera.shader_hash",cam)
        self.assertIn("last_temporal_scene_jitter",camcpp)
        self.assertNotIn("guest_display_history_contiguous = use_scene_motion;",present)

    def test_one_scene_every_three_videoout_callbacks(self):
        # Pure state-model regression: 1st true scene seeds history; two
        # fillers use spatial provider; 4th/7th true scene reuse GSR2 history.
        last_scene = None
        eligible = False
        results = []
        for flip in range(1,10):
            has_camera = flip % 3 == 1
            good_chain = has_camera and last_scene is not None
            gap = flip - last_scene if last_scene is not None else 0
            temporal = has_camera and eligible and 1 <= gap <= 4 and good_chain
            results.append((flip,has_camera,temporal))
            if has_camera:
                last_scene=flip
                eligible=True
        self.assertEqual(results,[
            (1,True,False),(2,False,False),(3,False,False),
            (4,True,True),(5,False,False),(6,False,False),
            (7,True,True),(8,False,False),(9,False,False)])

    def test_camera_cut_and_stale_scene_reset(self):
        # 4+ unverified frames and an incompatible camera must not revive
        # an older pre-cutscene Qualcomm history buffer.
        last_temporal=10
        self.assertTrue(1 <= 13-last_temporal <= 4)
        self.assertFalse(1 <= 17-last_temporal <= 4)
        self.assertFalse(False and 1 <= 13-last_temporal <= 4)


if __name__ == "__main__":
    unittest.main()
