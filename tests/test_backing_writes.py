"""Exercise the production backing-write methods without a Vulkan device."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BackingWriteTests(unittest.TestCase):
    def test_backing_writes_invalidate_only_stale_cpu_images(self):
        compiler = shutil.which('g++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        source = (ROOT / 'gpu/shadps4/video_core/texture_cache/texture_cache.cpp').read_text()
        begin = source.index('void TextureCache::NoteBackingWrite(')
        end = source.index('void TextureCache::InvalidateMemoryFromGPU(', begin)
        # Compile the actual implementation against an in-memory image registry.
        fixture = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>
using VAddr = uint64_t;
using u64 = uint64_t;
using ImageId = unsigned;
enum class ImageFlagBits : unsigned { CpuDirty=1, GpuModified=2, Aliased=4 };
ImageFlagBits operator|(ImageFlagBits a, ImageFlagBits b) {
    return ImageFlagBits(unsigned(a) | unsigned(b));
}
ImageFlagBits operator&(ImageFlagBits a, ImageFlagBits b) {
    return ImageFlagBits(unsigned(a) & unsigned(b));
}
ImageFlagBits& operator|=(ImageFlagBits& a, ImageFlagBits b) { return a = a | b; }
bool True(ImageFlagBits a) { return unsigned(a) != 0; }
struct Image {
    VAddr address;
    u64 size;
    ImageFlagBits flags;
    unsigned untracks = 0;
};
class TextureCache {
public:
    std::mutex backing_writes_mutex;
    std::vector<std::pair<VAddr, u64>> backing_writes;
    std::atomic<bool> has_backing_writes{false};
    std::vector<Image> images;
    void NoteBackingWrite(VAddr, u64);
    void ApplyBackingWrites();
    template<class F> void ForEachImageInRegion(VAddr address, u64 size, F f) {
        for (ImageId id = 0; id < images.size(); ++id) {
            auto& image = images[id];
            if (address < image.address + image.size && image.address < address + size)
                f(id, image);
        }
    }
    void UntrackImage(ImageId id) { ++images[id].untracks; }
};
'''
        checks = r'''
int main() {
    TextureCache cache;
    cache.images = {
        {0x1000, 0x100, ImageFlagBits(0)},
        {0x1080, 0x100, ImageFlagBits(0)},
        {0x1000, 0x100, ImageFlagBits::GpuModified},
        {0x1000, 0x100, ImageFlagBits::Aliased},
        {0x3000, 0x100, ImageFlagBits(0)},
    };
    cache.ApplyBackingWrites();
    assert(cache.images[0].untracks == 0);
    cache.NoteBackingWrite(0x1080, 0x20);
    assert(cache.has_backing_writes.load());
    assert(cache.images[0].untracks == 0); // deferred until cache safe point
    cache.ApplyBackingWrites();
    assert(!cache.has_backing_writes.load());
    assert(cache.backing_writes.empty());
    for (unsigned id : {0u, 1u}) {
        assert(True(cache.images[id].flags & ImageFlagBits::CpuDirty));
        assert(cache.images[id].untracks == 1);
    }
    for (unsigned id : {2u, 3u, 4u}) {
        assert(!True(cache.images[id].flags & ImageFlagBits::CpuDirty));
        assert(cache.images[id].untracks == 0);
    }
    cache.ApplyBackingWrites();
    assert(cache.images[0].untracks == 1); // no replay of drained writes
    std::vector<std::thread> producers;
    for (int i = 0; i < 4; ++i)
        producers.emplace_back([&] {
            for (int j = 0; j < 100; ++j) cache.NoteBackingWrite(0x3000, 16);
        });
    for (auto& producer : producers) producer.join();
    assert(cache.backing_writes.size() == 400);
    cache.ApplyBackingWrites();
    assert(cache.images[4].untracks == 400);
    assert(!cache.has_backing_writes.load());
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(fixture + source[begin:end] + checks)
            subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror',
                            '-pthread', str(path / 'test.cpp'), '-o', str(path / 'test')],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(path / 'test')], check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
