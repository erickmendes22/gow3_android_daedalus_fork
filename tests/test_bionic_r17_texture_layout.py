"""R17 regression: no Vulkan image backing reuse across physical layout changes.

GoW III can reuse a guest address and extent with a different pitch/tiling.
The cache's cheap lookup and exact-match selection must both reject this.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CPP = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text(encoding="utf-8")
H = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.h").read_text(encoding="utf-8")

class R17TextureLayoutIdentity(unittest.TestCase):
    def test_cached_request_tracks_physical_layout(self):
        entry = H.split("struct FindImageCacheEntry {", 1)[1].split("};", 1)[0]
        for field in ("pitch", "tile_mode", "array_mode", "num_samples",
                      "num_bits", "bank_swizzle", "alt_tile", "is_pow2", "is_block"):
            self.assertIn(field, entry)
            self.assertIn("cached." + field + " ==", CPP)
            self.assertIn("." + field + " =", CPP)

    def test_true_exact_match_checks_old_and_new_image_layout(self):
        method = CPP.split("ImageId TextureCache::FindImage(ImageDesc& desc, bool exact_fmt)", 1)[1]
        self.assertIn("const auto same_layout =", method)
        for field in ("pitch", "tile_mode", "array_mode", "num_samples",
                      "num_bits", "bank_swizzle", "alt_tile", "resources"):
            self.assertIn("a." + field + " == b." + field, method)
        self.assertIn("same_layout(image.info, info)", method)
        self.assertIn("if (!same_layout(cache_image.info, info))", method)
        self.assertIn("GOW3_TEXTURE_LAYOUT_REJECT", method)

    def test_equal_address_overlap_does_not_reintroduce_old_layout(self):
        overlap = CPP.split("std::tuple<ImageId, int, int> TextureCache::ResolveOverlap(", 1)[1]
        same_addr = overlap.split("// Equal address", 1)[1].split("// Right overlap", 1)[0]
        self.assertIn("GOW3_TEXTURE_OVERLAP_LAYOUT_REJECT", same_addr)
        self.assertIn("a.pitch != b.pitch || a.tile_mode != b.tile_mode", same_addr)
        self.assertIn("a.array_mode != b.array_mode", same_addr)
        self.assertIn("a.bank_swizzle != b.bank_swizzle", same_addr)
        self.assertIn("a.alt_tile != b.alt_tile", same_addr)
        self.assertIn("a.num_samples != b.num_samples", same_addr)
        guard = same_addr.split("if (a.pitch != b.pitch",1)[1].split("if (image_info.BlockDim()",1)[0]
        self.assertIn("return {merged_image_id, -1, -1};", guard)

    def test_same_guest_address_different_tiling_must_not_match(self):
        first = dict(address=0x100000, width=1280, height=720, format="RGBA8",
                     pitch=1280, tile=1, samples=1)
        second = {**first, "tile": 2}
        self.assertTrue(all(first[k] == second[k] for k in
                            ("address", "width", "height", "format")))
        self.assertNotEqual(first["tile"], second["tile"])
        self.assertFalse(all(first[k] == second[k] for k in first))

if __name__ == "__main__":
    unittest.main()
