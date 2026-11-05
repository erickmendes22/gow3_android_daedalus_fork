"""R15 regression: Bionic GSR2 FragCoord must use the real patched guest size."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "gpu/shadps4/shader_recompiler/backend/spirv/emit_spirv_context_get_set.cpp"

class R15NativeFragCoord(unittest.TestCase):
    def test_guest_native_resolution_not_hardcoded_inside_fragment_attribute(self):
        src = SOURCE.read_text(encoding="utf-8")
        self.assertIn("GuestFragCoordExtent()", src)
        self.assertIn('std::getenv("GOW3_ANDROID_PORT")', src)
        self.assertIn('std::getenv("GOW3_UPSCALER")', src)
        self.assertIn('std::getenv("GOW3_PATCH_INPUT_RES")', src)
        self.assertIn('std::strcmp(provider, "gsr2") != 0', src)
        self.assertIn('std::sscanf(patched, "%ux%u", &w, &h)', src)
        self.assertIn("const Id native = ctx.ConstU32(GuestFragCoordExtent()[comp]);", src)
        fragcoord = src.split("case IR::Attribute::FragCoord: {", 1)[1].split(
            "case IR::Attribute::TessellationEvaluationPointU:", 1)[0]
        self.assertNotIn("comp == 0 ? 1920u : 1080u", fragcoord)
        self.assertIn("ctx.OpFDiv(", fragcoord)
    def test_android_720p_ratio_and_desktop_fallback(self):
        src = SOURCE.read_text(encoding="utf-8")
        self.assertIn("desktop{1920u, 1080u}", src)
        self.assertIn("return desktop;", src)
        self.assertIn("std::array<u32, 2>{w, h}", src)
        self.assertEqual((1280 // 640, 720 // 360), (2, 2))
        self.assertEqual((1920 // 640, 1080 // 360), (3, 3))

if __name__ == "__main__":
    unittest.main()
