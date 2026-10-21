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
                self.assertEqual(up['GOW3_GSR2_DIRECT_VIDEOOUT'],'1')
                self.assertEqual(up['GOW3_GSR2_INPUT_RES'],raster)
                self.assertEqual(up['GOW3_PATCH_INPUT_RES'],raster)
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

    def test_shell_exports_host_separately_from_guest_raster(self):
        sh=(ROOT/'tools/android/bionic/run-bionic.sh').read_text()
        self.assertIn('GOW3_GSR2_DIRECT_VIDEOOUT:-0',sh)
        self.assertIn('export GOW3_OUTPUT_RES="${GOW3_GSR2_OUTPUT_RES:-1280x720}"',sh)
        self.assertIn('input=${GOW3_GSR2_INPUT_RES:-guest-native}',sh)

if __name__=='__main__':
    unittest.main()
