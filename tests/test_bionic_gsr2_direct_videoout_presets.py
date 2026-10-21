"""Verify GSR2 quality presets select byte-validated REAL guest render sizes."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import patches
import launch_env

IDENT={
    'title_id':'CUSA01623',
    'app_version':'01.02',
    'eboot_sha256':patches.CUSA01715_0102_ANDROID_SHA,
    'eboot_matches':True,'patch_sites_match':True,
    'reason':'validated',
}

class Gsr2DirectVideoOutPresets(unittest.TestCase):
    PRESETS={
        0:('1280x720','720p'),
        1:('960x540','540p'),
        2:('752x424','424p'),
        3:('640x360','360p'),
        4:('426x240','240p'),
    }

    def test_all_five_profiles_use_verified_eboot_raster_and_720p_host(self):
        for p,(raster,choice) in self.PRESETS.items():
            with self.subTest(preset=p),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                ini=folder/"gow3.ini"
                ini.write_text(f"upscaler=gsr2\npreset={p}\nrender_resolution=720p\n")
                with patch.object(patches,"patch_profile_status",return_value=IDENT):
                    plan=launch_env.derive(folder,ini,folder/"state.json",{"GOW3_ANDROID_PORT":"1"})
                up=plan['updates']
                self.assertEqual(up['GOW3_UPSCALER'],'gsr2')
                self.assertEqual(up['GOW3_PATCH_INPUT_RES'],raster)
                if p == 0:
                    # 1:1 native path was already fixed and must not change.
                    self.assertNotIn('GOW3_GSR2_DIRECT_VIDEOOUT',up)
                    self.assertEqual(up['GOW3_RESOLUTION_STATUS'],'verified-gsr2-720p-target')
                    self.assertEqual(up['GOW3_UPSCALER_SOURCE'],'gsr2-native-aa-1to1')
                else:
                    self.assertEqual(up['GOW3_GSR2_DIRECT_VIDEOOUT'],'1')
                    self.assertEqual(up['GOW3_GSR2_INPUT_RES'],raster)
                    self.assertEqual(up['GOW3_GSR2_OUTPUT_RES'],'1280x720')
                    self.assertEqual(up['GOW3_RESOLUTION_STATUS'],'verified-gsr2-videoout-input')
                    self.assertEqual(up['GOW3_UPSCALER_SOURCE'],'gsr2-verified-videoout')
                self.assertIn('Resolution Patch - 720p',plan['patch_names'])
                self.assertNotIn('render_resolution='+choice,ini.read_text() if choice!='720p' else '')
                self.assertIn('render_resolution=720p',ini.read_text())

    def test_wrong_eboot_is_not_allowed_to_use_direct_videoout_size(self):
        for reason,sha in [('validated','0'*64),('unverified-eboot',patches.CUSA01715_0102_ANDROID_SHA)]:
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp); ini=folder/'gow3.ini'
                ini.write_text('upscaler=gsr2\npreset=3\nrender_resolution=720p\n')
                ident={**IDENT,'reason':reason,'eboot_sha256':sha}
                with patch.object(patches,"patch_profile_status",return_value=ident):
                    plan=launch_env.derive(folder,ini,folder/'state.json',{"GOW3_ANDROID_PORT":"1"})
                self.assertNotIn('GOW3_GSR2_DIRECT_VIDEOOUT',plan['updates'])
                self.assertNotIn('GOW3_GSR2_INPUT_RES',plan['updates'])
                self.assertNotIn('GOW3_GSR2_OUTPUT_RES',plan['updates'])

    def test_sharpen_blit_uses_its_local_dimensions(self):
        # Regression: an overly broad w/h -> ow/oh replacement broke ARM64
        # compilation in ExtraSharpen(), which has only w and h parameters.
        cpp=(ROOT/'gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp').read_text()
        sharpen=cpp.split('void TemporalUpscaler::ExtraSharpen(',1)[1].split(
            'void TemporalUpscaler::OnBlendedSceneDraw(',1)[0]
        self.assertNotIn('s32(ow)',sharpen)
        self.assertNotIn('s32(oh)',sharpen)
        self.assertEqual(sharpen.count('vk::Offset3D{s32(w), s32(h), 1}'),2)
        source=cpp.split('bool TemporalUpscaler::PresentGsr2FromGuestDisplay(',1)[1].split(
            'bool TemporalUpscaler::DisplayOverride(',1)[0]
        self.assertIn('const u32 ow = target_width, oh = target_height;',source)
        self.assertIn('RecordGsr2(cmd, source_view, *guest_display_depth_view, w, h, ow, oh)',source)

    def test_direct_videoout_blit_copies_full_gsr2_output_not_quarter_screen(self):
        # 640x360->1280x720 must copy the entire computed output into the
        # presented 1280x720 UI image. Using input w/h here painted 1/4 screen.
        cpp=(ROOT/'gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp').read_text()
        source=cpp.split('bool TemporalUpscaler::PresentGsr2FromGuestDisplay(',1)[1].split(
            'bool TemporalUpscaler::DisplayOverride(',1)[0]
        blit=source.split('const vk::ImageBlit region{',1)[1].split(
            'cmd.blitImage(',1)[0]
        self.assertEqual(blit.count('vk::Offset3D{s32(ow), s32(oh), 1}'),2)
        self.assertNotIn('vk::Offset3D{s32(w), s32(h), 1}',blit)
        self.assertIn('display = {vk::Image(ui_image), source.info.pixel_format, ow, oh}',source)

    def test_completed_scene_temporal_inputs_are_real_and_frame_aligned(self):
        cpp=(ROOT/'gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp').read_text()
        cam=(ROOT/'gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp').read_text()
        cam_h=(ROOT/'gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.h').read_text()
        videoout=cpp.split('bool TemporalUpscaler::PresentGsr2FromGuestDisplay(',1)[1].split(
            'bool TemporalUpscaler::DisplayOverride(',1)[0]
        on_display=cam.split('void CameraMotion::OnDisplayPass(',1)[1].split(
            'void CameraMotion::Overlay(',1)[0]
        self.assertLess(on_display.index('completed_history_status ='),
                        on_display.index('current.valid = false;'))
        self.assertLess(on_display.index('completed_depth = depth_id;'),
                        on_display.index('depth_id = {};'))
        self.assertIn('completed_current = current;', on_display)
        self.assertIn('completed_previous = previous;', on_display)
        self.assertIn('CompletedHistoryValidity()',videoout)
        self.assertIn('CompletedDepth()',videoout)
        self.assertIn('RecordCompletedMotion(cmd, chosen_depth_view, *motion_view, w, h)',videoout)
        self.assertIn('CachedView(real_depth, real_depth.info.pixel_format',videoout)
        self.assertIn('guest_display_history_contiguous = use_scene_motion;',videoout)
        self.assertIn('guest_display_history_contiguous = false;',cpp)
        self.assertIn('guest_display_history_contiguous',cpp)
        self.assertIn('completed_history_status = Gsr2HistoryStatus::MissingCamera',cam_h)
        self.assertIn('completed_depth',cam_h)
        self.assertIn('RecordMotionFor(cmdbuf, depth_view, motion_view, width, height,',cam)
        self.assertIn('completed_current, completed_previous, {}, {}, false)',cam)
        self.assertIn('guest_display_motion_ready = use_scene_motion;',videoout)
        self.assertIn('guest_display_motion_ready)',cpp)
        self.assertIn('chosen_depth_view, w, h, ow, oh',videoout)
        # No unconditional spatial-only guard for the direct VideoOut route.
        record=cpp.split('bool TemporalUpscaler::RecordGsr2(',1)[1].split(
            'bool TemporalUpscaler::UseDlss()',1)[0]
        self.assertNotIn('!guest_display_mode_recording &&',record)
        self.assertIn('!guest_display_history_contiguous',record)

    def test_shell_exports_host_separately_from_guest_raster(self):
        sh=(ROOT/'tools/android/bionic/run-bionic.sh').read_text()
        self.assertIn('GOW3_GSR2_DIRECT_VIDEOOUT:-0',sh)
        self.assertIn('export GOW3_OUTPUT_RES="${GOW3_GSR2_OUTPUT_RES:-1280x720}"',sh)
        self.assertIn('input=${GOW3_GSR2_INPUT_RES:-guest-native}',sh)

if __name__=='__main__':
    unittest.main()
