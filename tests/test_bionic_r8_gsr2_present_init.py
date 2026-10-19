"""R8: enforce full display coverage and late, bounded GSR2 forensic captures."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
def read(path): return (ROOT / path).read_text(encoding="utf-8")
class R8(unittest.TestCase):
    def test_r8_only_gsr2_allocates_blittable_display(self):
        c=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        self.assertIn("eTransferSrc | vk::ImageUsageFlagBits::eTransferDst",c)
        self.assertIn('std::getenv("GOW3_GSR2_PREFILL_DISPLAY")',c)
        self.assertIn("const bool prefill_gsr2 = UseGsr2()",c)
        self.assertIn("vk::ImageLayout::eTransferSrcOptimal",c)
        self.assertIn("vk::ImageLayout::eTransferDstOptimal",c)
        self.assertIn("GSR2_PRESENT_INIT copied full UI",c)
        self.assertIn("cmd.blitImage(source, vk::ImageLayout::eTransferSrcOptimal,",c)
        self.assertIn(".srcOffsets = std::array{vk::Offset3D{}, vk::Offset3D{s32(ui_width)",c)
        self.assertIn(".dstOffsets = std::array{vk::Offset3D{}, vk::Offset3D{s32(display.width)",c)
        self.assertIn("display.valid = true;",c)
    def test_capture_mature_frames_and_actual_presenter(self):
        s=read("gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp")
        p=read("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
        for keyword in ("gsr_probe_frames == 480", "gsr_probe_frames == 2400",
                        "gsr_probe_frames == 7200", "GSR2_DISPLAY_DRAW",
                        "GSR2_PRESENT_QUERY"):
            self.assertIn(keyword,s)
        self.assertIn("GSR2_PRESENTER actual_guest=",p)
        self.assertIn("int(upscaled)",p)
        self.assertIn("GsrProbeGrid(",s)
        script=read("tools/android/bionic/run-bionic.sh")
        self.assertIn("export GOW3_GSR2_PREFILL_DISPLAY=1",script)
    def test_one_gated_ci(self):
        ci=read(".github/workflows/bionic-apk.yml")
        self.assertIn("r8-build-trigger.txt",ci)
        self.assertIn("fix/bionic-r8-gsr2-present-init-20261019",ci)
if __name__=="__main__": unittest.main()
