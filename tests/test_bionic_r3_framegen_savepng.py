"""Regression guards for R3 on Adreno 830 / Android save PNGs.

The ARM64 Bionic native compilation in CI verifies the actual C++ code.
On-device behaviour must still be checked before calling the bugs fixed.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def source(rel):
    return (ROOT / rel).read_text(encoding="utf-8")

class BionicR3Tests(unittest.TestCase):
    def test_adreno_830_avoids_external_sync_fd_by_default(self):
        cpp = source("gpu/shadps4/video_core/renderer_vulkan/gow3_lsfg.cpp")
        self.assertIn('gpu_name.find("Adreno (TM) 830")', cpp)
        self.assertIn("sync_mode.empty()", cpp)
        self.assertIn('sync_mode == "host" || turnip_gen8_workaround', cpp)
        self.assertIn('GOW3_LSFG_SYNC=fd', cpp)
        self.assertIn('const bool chained = Chained()', cpp)
        # CPU handoff must wait for the submitted copy before calling Bloodframe.
        self.assertIn('if (sync_host)', cpp)
        self.assertIn('device.waitForFences(copy_done, VK_TRUE, WaitNs)', cpp)
        self.assertIn('if (api->wait(ctx.id, WaitNs) != 0)', cpp)

    def test_real_save_images_decode_via_android_with_ffmpeg_fallback(self):
        png = source("gpu/shim/gow3_png.cpp")
        self.assertIn('#if defined(__ANDROID__)', png)
        self.assertIn('dlopen("libjnigraphics.so"', png)
        for symbol in ('AImageDecoder_createFromBuffer',
                       'AImageDecoder_getHeaderInfo',
                       'AImageDecoder_setAndroidBitmapFormat',
                       'AImageDecoder_decodeImage'):
            self.assertIn(symbol, png)
        self.assertIn('if (DecodeAndroidPng(data, size, out)) return true;', png)
        self.assertIn('avcodec_send_packet(context, packet)', png)
        self.assertIn('avcodec_receive_frame(context, frame)', png)

    def test_preview_source_is_actual_save_art_not_a_fake_tile(self):
        saves = source("src/runtime_savedata.c")
        self.assertIn('"%s/%s.sce_sys/icon0.png"', saves)
        self.assertIn('"%s/%s/sce_sys/icon0.png"', saves)
        self.assertIn('!memcmp(sig,"\\x89PNG\\r\\n\\x1a\\n",8)', saves)
        overlay = source("gpu/shim/gow3_overlay.cpp")
        self.assertIn("choice_pictures = std::move(pictures);", overlay)
        self.assertIn('ImGui::RegisterUserTexture(tex);', overlay)
        self.assertIn('No save preview', overlay)

if __name__ == "__main__":
    unittest.main()
