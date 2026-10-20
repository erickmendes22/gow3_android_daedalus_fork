"""R19 regression: Native AA remains 1:1 GSR2 and native texture coherence is preserved.

The GSR2 Native-AA preset is NOT the same thing as disabling AA. The guest
720p scene is processed at 720p without SceneTargets reduction or enlargement.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UP = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp").read_text()
SCENE = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/scene_resolution.h").read_text()
CACHE = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()
LAUNCH = (ROOT / "scripts/launch_env.py").read_text()


class NativeAaTextureRegression(unittest.TestCase):
    def test_native_aa_uses_provider_without_reduction(self):
        self.assertIn("ini.get('upscaler') == 'gsr2'", LAUNCH)
        self.assertIn("graphics.get('render_resolution') != '8K'", LAUNCH)
        self.assertIn("'gsr2-native-aa-1to1'", LAUNCH)
        self.assertIn("scales{1.0, 1.5, 1.7, 2.0, 3.0}", SCENE)
        boundary = UP.split("void TemporalUpscaler::OnDisplayBoundary(", 1)[1].split(
            "void TemporalUpscaler::OnDraw(", 1)[0]
        self.assertIn("Gow3Settings::RenderPreset() == Gow3Settings::NativeAA", boundary)
        self.assertIn("!scene_targets.Reduced()", boundary)
        self.assertIn("render_width == target_width", boundary)
        self.assertIn("render_height == target_height", boundary)
        self.assertIn("(native_aa || true_upscale)", boundary)
        self.assertIn("RunScaled();", boundary)

    def test_native_aa_uses_original_input_images_not_fake_proxies(self):
        scaled = UP.split("void TemporalUpscaler::RunScaled() {", 1)[1].split(
            "void TemporalUpscaler::", 1)[0]
        self.assertIn("if (!scaled_session && scene_targets.Reduced())", scaled)
        self.assertIn("scene_targets.Read(ldr_target, ci)", scaled)
        self.assertIn("color_view = CachedView(color, color.info.pixel_format", scaled)
        self.assertIn("depth_view = CachedView(depth, depth_format", scaled)
        self.assertIn("runtime.Transit(&color,", scaled)
        self.assertIn("runtime.Transit(&depth,", scaled)
        self.assertIn("RecordGsr2(cmdbuf, color_view, depth_view, w, h, ow, oh)", scaled)

    def test_cpu_invalidation_drops_stale_hash(self):
        invalid = CACHE.split("void TextureCache::InvalidateMemory(", 1)[1].split(
            "void TextureCache::NoteBackingWrite(", 1)[0]
        self.assertIn("InvalidateAlias(image);", invalid)
        self.assertIn("image.hash = 0;", invalid)
        self.assertIn("image.flags |= ImageFlagBits::CpuDirty;", invalid)
        refresh = CACHE.split("void TextureCache::RefreshImage(", 1)[1].split(
            "void TextureCache::", 1)[0]
        self.assertIn("XXH3_64bits(addr, image.info.guest_size)", refresh)
        self.assertNotIn("const u32 w = std::min(image.info.size.width, u32(8));", refresh)

    def test_still_reject_incompatible_non_depth_layout(self):
        overlap = CACHE.split("std::tuple<ImageId, int, int> TextureCache::ResolveOverlap(", 1)[1].split(
            "ImageId TextureCache::ExpandImage(", 1)[0]
        self.assertIn("const bool depth_conversion =", overlap)
        self.assertIn("if (!depth_conversion &&", overlap)
        self.assertIn("a.props.is_depth != b.props.is_depth", overlap)
        self.assertIn("GOW3_TEXTURE_OVERLAP_LAYOUT_REJECT", overlap)
        self.assertIn("ResolveDepthOverlap(image_info, binding, cache_image_id)", overlap)


if __name__ == "__main__":
    unittest.main()
