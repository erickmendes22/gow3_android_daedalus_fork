"""GSR2: actual Android direct VideoOut capture and Bloodborne history filter."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
GPU=ROOT/'gpu/shadps4/video_core'
CPP=GPU/'renderer_vulkan/vk_temporal_upscaler.cpp'
GSR=GPU/'renderer_vulkan/vk_gsr2.cpp'
SHADER=GPU/'host_shaders/gsr2_upscale.comp'
APP=ROOT/'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java'
RUN=ROOT/'tools/android/bionic/run-bionic.sh'

class Gsr2CaptureHistory(unittest.TestCase):
    def test_bloodborne_catmull_rom_is_wired_through_64_byte_params(self):
        shader=SHADER.read_text()
        native=GSR.read_text()
        self.assertIn("vec3 SampleHistoryCatmullRom(vec2 uv)",shader)
        self.assertIn("params.historyFilter != 0u ? SampleHistoryCatmullRom(PrevUV)",shader)
        self.assertIn("invalidReprojection",shader)
        self.assertIn("uint  historyFilter;",shader)
        self.assertIn("u32 history_filter;",native)
        self.assertIn("static_assert(sizeof(Params) == 64)",native)
        self.assertIn("params.history_filter =",native)
        self.assertIn('GOW3_GSR2_HISTORY',native)

    def test_direct_videoout_dumps_same_dispatch_complete_input_set(self):
        src=CPP.read_text()
        a=src.index("bool TemporalUpscaler::PresentGsr2FromGuestDisplay(")
        b=src.index("bool TemporalUpscaler::DisplayOverride(",a)
        direct=src[a:b]
        self.assertIn("GSR2_CAPTURE_FRAME index=",direct)
        self.assertIn('"input",fmt',direct)
        self.assertIn('"videoout",fmt',direct)
        self.assertIn('"motion","rg16f"',direct)
        self.assertIn('"depth","r32f",vk::ImageAspectFlagBits::eColor',direct)
        self.assertIn('"output","rgba16f"',direct)
        self.assertIn('"composited","rgba_unorm"',direct)
        self.assertIn("bool force_raw = false",src)
        self.assertIn("!force_raw && std::getenv",src)

    def test_capture_waits_for_actual_temporal_history(self):
        src=CPP.read_text()
        self.assertIn("int DumpFrame(bool eligible = true)",src)
        self.assertIn("if (!trigger || !eligible)",src)
        self.assertIn("DumpFrame(reuse_history)",src)
        app=APP.read_text()
        self.assertIn("skipping spatial fallback frames",app)
        self.assertIn("ONLY successful temporal history frames (reset=0)",app)

    def test_in_game_menu_can_capture_and_export_without_root(self):
        app=APP.read_text()
        self.assertIn("Capture GSR2 temporal scaling",app)
        self.assertIn("Export GSR2 capture ZIP",app)
        self.assertIn("void startGsr2Capture()",app)
        self.assertIn("void writeGsr2CaptureZip(",app)
        self.assertIn("Intent.ACTION_CREATE_DOCUMENT",app)
        self.assertIn('"frames/"+file.getName()',app)
        self.assertIn("new ZipEntry(\"logs/android-game.log\")",app)
        runtime=RUN.read_text()
        self.assertIn('export GOW3_DUMP_DIR="$base/out/gsr2-capture"',runtime)
        self.assertIn('export GOW3_DUMP_TRIGGER="$base/gsr2-capture.trigger"',runtime)
        self.assertIn('export GOW3_DUMP_FRAMES=6',runtime)

if __name__=='__main__':
    unittest.main()
