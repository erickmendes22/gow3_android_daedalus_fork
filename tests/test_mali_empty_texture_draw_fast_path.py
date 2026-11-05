"""Prevent wasted helper-thread synchronization on image-free GoW3 draws.

The fast path must retain independent sampler descriptors and must not bypass
the existing safety checks for storage textures or dynamic mip arrays.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()


def method(begin: str, end: str) -> str:
    start = SRC.index(begin)
    stop = SRC.index(end, start + len(begin))
    return SRC[start:stop]


class EmptyTextureDrawFastPathTest(unittest.TestCase):
    def test_worker_only_when_stage_has_images(self):
        helper = method("bool Rasterizer::HelperEligible(", "bool Rasterizer::TexturesBindableOnHelper(")
        self.assertIn("bool has_textures = false;", helper)
        self.assertIn("has_textures |= !stage->images.empty();", helper)
        self.assertIn("return has_textures;", helper)
        self.assertIn("stage->images", helper)
        self.assertIn("stage->buffers", helper)
        self.assertIn("Gow3Toggle::TextureBindHelper", helper)
        self.assertIn("Gow3Toggle::UpdateImageFastPath", helper)

    def test_empty_stage_binds_sampler_on_owner_and_exits_before_texture_memo(self):
        binder = method("void Rasterizer::BindTextures(", "void Rasterizer::BindSamplers(")
        self.assertRegex(binder, r"if \(stage\.images\.empty\(\)\)\s*\{\s*BindSamplers\(stage, prepared, binding, write_index\);\s*return;")
        self.assertLess(binder.index("if (stage.images.empty())"),
                        binder.index("BindTexturesFromSet("))
        self.assertLess(binder.index("if (stage.images.empty())"),
                        binder.index("image_bindings.clear();"))

    def test_draws_with_images_keep_worker_eligibility_safety(self):
        helper = method("bool Rasterizer::HelperEligible(", "bool Rasterizer::TexturesBindableOnHelper(")
        self.assertRegex(helper, r"if \(image\.mip_fallback_mode != Shader::MipStorageFallbackMode::None\)")
        self.assertRegex(helper, r"if \(!buffer\.IsSpecial\(\) && buffer\.is_written\)")
        self.assertIn("return false;", helper)


if __name__ == "__main__":
    unittest.main()
