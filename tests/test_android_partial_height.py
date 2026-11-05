"""Exercise the production reuse condition, including the exposure regression guards."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import paths

ROOT = paths.ROOT
SOURCE = ROOT / 'gpu/shadps4/video_core/texture_cache/texture_cache.cpp'


class PartialHeightTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('c++'), 'C++ compiler required')
    def test_production_reuse_condition(self):
        source = SOURCE.read_text()
        condition = re.search(r'if \((partial_views_enabled &&.*?)\) \{', source, re.S)[1]
        program = r'''
#include <cassert>
#include <cstdint>
enum class BindingType { Texture, Storage, RenderTarget, DepthTarget, VideoOut };
namespace Gow3Toggle {
constexpr auto PartialHeightViews = 1ull << 58;
bool disabled = false;
bool Disabled(std::uint64_t) { return disabled; }
}
struct Info {
    int pixel_format = 1, pitch = 1920, tile_mode = 1, type = 1;
    struct { int width = 1920, height = 1080, depth = 1; } size;
    struct { int levels = 1, layers = 1; } resources;
    struct { bool is_block = false, is_depth = false; } props;
};
bool compatible = true;
bool IsVulkanFormatCompatible(int, int) { return compatible; }
bool is_integer(int format) { return format == 2 || format == 3; }
bool reuse(const Info& a, const Info& b, BindingType binding = BindingType::Texture,
           bool native_reads = true, bool partial_views_enabled = true,
           int lhs_block_size = 32, int rhs_block_size = 32) {
    return CONDITION;
}
int main() {
    Info request, cached;
    request.pixel_format = 2;
    request.size.height = 800;
    assert(reuse(request, cached));
    assert(reuse(request, cached, BindingType::Storage));
    request.pixel_format = 3; assert(reuse(request, cached));
    request.pixel_format = 2;
    // Normalized coordinates and same-format pool reuse caused blown exposure upstream.
    assert(!reuse(request, cached, BindingType::Texture, false));
    request.pixel_format = 1; assert(!reuse(request, cached));
    request.pixel_format = 4; assert(!reuse(request, cached));
    request.pixel_format = 2;
    assert(!reuse(request, cached, BindingType::RenderTarget));
    assert(!reuse(request, cached, BindingType::DepthTarget));
    assert(!reuse(request, cached, BindingType::VideoOut));
    assert(!reuse(request, cached, BindingType::Texture, true, false));
    assert(!reuse(request, cached, BindingType::Texture, true, true, 64, 32));
    Gow3Toggle::disabled = true; assert(!reuse(request, cached));
    Gow3Toggle::disabled = false;
    compatible = false; assert(!reuse(request, cached)); compatible = true;
    auto reject = [&](auto change) {
        auto a = request, b = cached;
        change(a, b);
        assert(!reuse(a, b));
    };
    reject([](auto& a, auto&) { a.pitch++; });
    reject([](auto& a, auto&) { a.tile_mode++; });
    reject([](auto& a, auto&) { a.type++; });
    reject([](auto& a, auto&) { a.size.width++; });
    reject([](auto& a, auto& b) { a.size.height = b.size.height; });
    reject([](auto& a, auto& b) { a.size.height = b.size.height + 1; });
    reject([](auto& a, auto&) { a.size.depth++; });
    reject([](auto&, auto& b) { b.size.depth++; });
    reject([](auto& a, auto&) { a.resources.levels++; });
    reject([](auto&, auto& b) { b.resources.levels++; });
    reject([](auto& a, auto&) { a.resources.layers++; });
    reject([](auto&, auto& b) { b.resources.layers++; });
    reject([](auto& a, auto&) { a.props.is_block = true; });
    reject([](auto&, auto& b) { b.props.is_block = true; });
    reject([](auto& a, auto&) { a.props.is_depth = true; });
    reject([](auto&, auto& b) { b.props.is_depth = true; });
}
'''.replace('CONDITION', condition)
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'reuse.cpp'
            executable = Path(directory) / 'reuse'
            cpp.write_text(program)
            subprocess.run(['c++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                            str(cpp), '-o', str(executable)], check=True, capture_output=True)
            subprocess.run([str(executable)], check=True, capture_output=True)

    def test_both_cache_keys_keep_coordinate_semantics(self):
        source = SOURCE.read_text()
        rasterizer = (ROOT / 'gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp').read_text()
        self.assertIn('cached.needs_native == desc.needs_native', source)
        self.assertIn('u64(desc.needs_native) << 62', source)
        self.assertIn('u32(res.needs_native) << 3', rasterizer)
        self.assertIn('ResolveOverlap(merged_info, desc.type, cache_id, image_id, desc.needs_native)', source)


if __name__ == '__main__':
    unittest.main()
