"""Run emitted ARM64 code and exercise cache/range persistence contracts."""
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

import paths

try:
    import unicorn
    from unicorn import arm64_const as arm
except ImportError:
    unicorn = None

ROOT = paths.ROOT
INCLUDES = ROOT / 'gpu/shadps4'


def build(source, directory, name, extra=()):
    cpp = Path(directory) / (name + '.cpp')
    exe = Path(directory) / name
    cpp.write_text(source)
    subprocess.run(['c++', '-std=c++23', '-O2', '-Wall', '-Wextra', '-Werror',
                    *extra, '-I', str(INCLUDES), str(cpp), '-o', str(exe)], check=True, capture_output=True)
    return exe


@unittest.skipUnless(shutil.which('c++'), 'C++ compiler required')
class BachataOptimizationTests(unittest.TestCase):
    def test_native_fault_falls_back_and_keeps_cache_layout(self):
        cpp = (INCLUDES / 'shader_recompiler/ir/passes/flatten_extended_userdata_pass.cpp').read_text()
        start = cpp.index('struct NativeSrtCode {')
        end = cpp.index('\n} // namespace Shader', cpp.index('void RunSrtProgram(', start))
        actual = cpp[start:end]
        source = r'''
#include <atomic>
#include <vector>
#include <memory>
#include <mutex>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <cassert>
#include <csignal>
#include <csetjmp>
#include <sys/mman.h>
#include <unistd.h>
#include "shader_recompiler/ir/passes/srt_arm64.h"
#define ARCH_ARM64 1
#define LOG_WARNING(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
#define UNREACHABLE_MSG(...) std::abort()
using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
thread_local sigjmp_buf* runtime_fault_recover = nullptr;
using namespace Shader::Arm64Srt;
namespace Shader {
struct SrtProgram;
struct SrtWalker { SrtProgram* program{}; };
using PFN_SrtWalker = SrtWalker;
static_assert(sizeof(SrtWalker) == sizeof(void*));
void RunSrtProgram(const u32*, const u32*, u32*);
ACTUAL
}
static int calls;
void failing(const u32*, u32* flat) { ++calls; flat[16] = 999; std::raise(SIGSEGV); }
void working(const u32* data, u32* flat) { ++calls; flat[16] = data[4]; }
int main() {
    using namespace Shader;
    std::signal(SIGSEGV, [](int) { assert(runtime_fault_recover); siglongjmp(*runtime_fault_recover, 1); });
    u32 data[32]{}, flat[32]{}; data[4] = 33;
    SrtProgram stored{{SrtMagic, OpCopyImm, 4, 16, OpEnd}, nullptr};
    NativeSrtCode native; native.function = failing; stored.native = &native;
    sigjmp_buf previous; runtime_fault_recover = &previous;
    RunSrtWalker(&stored, data, flat);
    assert(flat[16] == 33 && calls == 1 && !native.enabled);
    assert(runtime_fault_recover == &previous);
    RunSrtWalker(&stored, data, flat); assert(calls == 1);
    native.enabled = true; native.function = working;
    RunSrtWalker(&stored, data, flat); assert(calls == 2 && flat[16] == 33);
    assert(runtime_fault_recover == &previous);
    assert(std::memcmp(SrtProgramCode(&stored), stored.words.data(), stored.words.size()*4) == 0);
    // Re-register the existing bytecode cache without executing ARM64 instructions on x86.
    auto loaded = RegisterWalkerCode(reinterpret_cast<const u8*>(stored.words.data()), stored.words.size()*4);
    assert(loaded.program && loaded.program->native);
    assert(std::memcmp(SrtProgramCode(loaded.program), stored.words.data(), stored.words.size()*4) == 0);
}
'''.replace('ACTUAL', actual)
        with tempfile.TemporaryDirectory() as directory:
            exe = build(source, directory, 'fallback', ('-Wno-clobbered',))
            subprocess.run([str(exe)], check=True, capture_output=True)

    @unittest.skipUnless(unicorn, 'Unicorn ARM64 execution engine required')
    def test_native_srt_instructions(self):
        source = r'''
#include <iostream>
#include "shader_recompiler/ir/passes/srt_arm64.h"
int main() {
    std::vector<std::uint32_t> words;
    std::uint32_t value;
    while (std::cin.read(reinterpret_cast<char*>(&value), 4)) words.push_back(value);
    auto out = Shader::Arm64Srt::Compile(words);
    std::cout.write(reinterpret_cast<const char*>(out.data()), std::streamsize(out.size() * 4));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            exe = build(source, directory, 'srt')

            def run(ops, flat=None, userdata=None, memory=None):
                data = struct.pack('<' + 'I' * (len(ops) + 2), 0x42545253, *ops, 0)
                code = subprocess.run([str(exe)], input=data, capture_output=True, check=True).stdout
                self.assertTrue(code)
                uc = unicorn.Uc(unicorn.UC_ARCH_ARM64, unicorn.UC_MODE_ARM)
                for address in (0x10000, 0x20000, 0x30000, 0x40000): uc.mem_map(address, 0x10000)
                uc.mem_write(0x10000, code)
                uc.mem_write(0x20000, struct.pack('<256I', *(userdata or [0] * 256)))
                initial = flat or [0] * 256
                uc.mem_write(0x30000, struct.pack('<256I', *initial))
                if memory:
                    for address, blob in memory.items(): uc.mem_write(address, blob)
                uc.reg_write(arm.UC_ARM64_REG_X0, 0x20000)
                uc.reg_write(arm.UC_ARM64_REG_X1, 0x30000)
                uc.reg_write(arm.UC_ARM64_REG_SP, 0x4f000)
                uc.reg_write(arm.UC_ARM64_REG_LR, 0x18000)
                for reg in range(19, 30): uc.reg_write(getattr(arm, 'UC_ARM64_REG_X' + str(reg)), reg * 99)
                uc.emu_start(0x10000, 0x18000, count=100000)
                self.assertEqual(uc.reg_read(arm.UC_ARM64_REG_PC), 0x18000)
                self.assertEqual(uc.reg_read(arm.UC_ARM64_REG_SP), 0x4f000)
                for reg in range(19, 30):
                    self.assertEqual(uc.reg_read(getattr(arm, 'UC_ARM64_REG_X' + str(reg))), reg * 99)
                self.last_srt_value = struct.unpack('<I', bytes(uc.mem_read(0x4f000 - 128, 4)))[0]
                return list(struct.unpack('<256I', bytes(uc.mem_read(0x30000, 1024))))

            # Every arithmetic opcode, including shifts >=32 and unsigned min/max.
            rng = random.Random(713)
            for opcode in range(9, 20):
                if opcode == 17: continue
                for a, b in [(0, 0), (0xffffffff, 32), (0x80000000, 31)] + [
                        (rng.getrandbits(32), rng.getrandbits(32)) for _ in range(5)]:
                    values = {9: a + b, 10: a - b, 11: a * b, 12: a << (b & 31),
                              13: a >> (b & 31), 14: a & b, 15: a | b, 16: a ^ b,
                              18: min(a, b), 19: max(a, b)}
                    # Dynamic copy offset consumes the arithmetic result; compare memory read.
                    expected = values[opcode] & 0xffffffff
                    # Test through a zeroed dynamic copy (consumes value without invalid reads).
                    self.assertEqual(run([8, a, 8, b, opcode, 0x80000005, 40])[40], 0)
                    self.assertEqual(self.last_srt_value, expected)
                    # Also use result as a pointer-table index, bounded to mapped data.
                    userdata = list(range(256))
                    ops = [8, a, 8, b, opcode, 8, 255, 14, 5, 41]
                    self.assertEqual(run(ops, userdata=userdata)[41], expected & 255)
            self.assertEqual(run([8, 0xfffffffa, 17, 5, 42], userdata=list(range(256)))[42], 5)
            self.assertEqual(run([8, 0xabcdef01, 8, 8, 8, 12, 20, 8, 255, 14, 5, 43],
                                 userdata=list(range(256)))[43], 0xef)
            # Nested pointers, 48-bit masking, dynamic offsets and both flat-data loads.
            user = [0] * 256
            user[0], user[1] = 0x21000, 0xabcd0000
            memory = {0x21000: struct.pack('<4I', 99, 0x22000, 0, 77),
                      0x22000: struct.pack('<2I', 123, 456)}
            flat = [0] * 256
            flat[2] = 1
            ops = [1, 0, 4, 0, 50, 6, 2, 2, 4, 1, 51, 3, 7, 2, 5, 52, 3]
            result = run(ops, flat=flat, userdata=user, memory=memory)
            self.assertEqual([result[i] for i in (50, 51, 52)], [99, 456, 0x22000])
            # Fault-disabled opcodes avoid accessing an invalid pointer.
            self.assertEqual(run([0x80000001, 0, 0x80000004, 9999, 60, 3])[60], 0)
            for invalid in ([0x42545253, 3, 0], [0x42545253, 8, 1],
                            [0x42545253, 8, 1, 0], [0x42545253, 99, 0]):
                out = subprocess.run([str(exe)], input=struct.pack('<' + 'I' * len(invalid), *invalid),
                                     capture_output=True, check=True).stdout
                self.assertFalse(out)

    def test_cache_identity_corruption_and_atomic_replace(self):
        source = r'''
#include <cassert>
#include "video_core/renderer_vulkan/driver_cache_file.h"
int main(int argc, char** argv) {
    assert(argc == 2);
    using namespace Vulkan::DriverCacheFile;
    Identity id{0x5143, 0x44050001, 123, {1,2,3}};
    std::vector<std::uint8_t> payload(64);
    std::uint32_t header[]{32, 1, id.vendor, id.device};
    std::memcpy(payload.data(), header, 16);
    std::memcpy(payload.data() + 16, id.uuid.data(), 16);
    auto encoded = Encode(payload, id);
    assert(Decode(encoded, id) == payload);
    auto other = id; other.driver++; assert(Decode(encoded, other).empty());
    other = id; other.uuid[0]++; assert(Decode(encoded, other).empty());
    other = id; other.device++; assert(Decode(encoded, other).empty());
    encoded.back() ^= 1; assert(Decode(encoded, id).empty());
    encoded.pop_back(); assert(Decode(encoded, id).empty());
    auto file = std::filesystem::path(argv[1]) / "cache" / "0.bin";
    assert(Save(file, payload, id)); assert(Load(file, id) == payload);
    payload.back()++; assert(Save(file, payload, id)); assert(Load(file, id) == payload);
    assert(!std::filesystem::exists(file.string() + ".tmp"));
    assert(!Save(file, std::span<const std::uint8_t>{}, id));
    assert(Load(file, id) == payload);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            exe = build(source, directory, 'cache_test')
            subprocess.run([str(exe), directory], check=True, capture_output=True)

    def test_copy_range_union_keeps_holes_and_rejects_overflow(self):
        source = r'''
#include <cassert>
#include "video_core/buffer_cache/copy_ranges.h"
int main() {
    using namespace VideoCore;
    const CopyRange ranges[]{{12288,4},{0,16},{8,24},{4096,8},{0,8},{5000,0}};
    const auto result = NormalizeCopyRanges(16384, ranges);
    assert(result && (*result == std::vector<CopyRange>{{0,32},{4096,8},{12288,4}}));
    const CopyRange overflow[]{{0xfffffff0,32}};
    assert(!NormalizeCopyRanges(0xffffffff, overflow));
    const CopyRange outside[]{{16,1}};
    assert(!NormalizeCopyRanges(16, outside));
    const CopyRange adjacent[]{{0,8},{8,8}};
    assert((NormalizeCopyRanges(16,adjacent) == std::vector<CopyRange>{{0,16}}));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            exe = build(source, directory, 'ranges')
            subprocess.run([str(exe)], check=True, capture_output=True)

    def test_range_page_locks_are_unique_and_protection_follows_upload(self):
        source = (INCLUDES / 'video_core/buffer_cache/memory_tracker.h').read_text()
        start = source.index('    void ForEachUploadRanges(')
        end = source.index('    /// Call', start)
        method = source[start:end]
        source = r'''
#include <cassert>
#include <mutex>
#include <set>
#include <array>
#include "video_core/buffer_cache/copy_ranges.h"
using u64 = std::uint64_t;
using VAddr = u64;
using namespace VideoCore;
enum class Type { CPU, GPU };
struct LockType {
    bool held = false;
    void lock() { assert(!held); held = true; }
    void unlock() { assert(held); held = false; }
};
struct RegionManager {
    LockType lock;
    u64 address{};
    std::set<u64> cpu_pages{0,1,2,3};
    std::vector<CopyRange> gpu;
    u64 GetCpuAddr() const { return address; }
    template<Type, bool> void ForEachModifiedRange(u64 at, u64 size, auto&& func) {
        assert(lock.held);
        for (auto page = (at-address)/4096; page < (at-address+size+4095)/4096; ++page) {
            if (cpu_pages.erase(page)) func(address+page*4096,4096);
        }
    }
    template<Type, bool> void ChangeRegionState(u64 at, u64 size) {
        assert(lock.held); gpu.emplace_back(std::uint32_t(at-address),std::uint32_t(size));
    }
};
class Tracker {
public:
    std::array<RegionManager,2> regions;
    Tracker() { regions[1].address = 65536; }
    template<bool> void IteratePages(u64 at, u64 size, auto&& func) {
        while(size) {
            auto index = at/65536, offset = at%65536, length = std::min(size,65536-offset);
            func(&regions[index], offset, length); size-=length; at+=length;
        }
    }
METHOD
};
int main() {
    Tracker tracker;
    const CopyRange ranges[]{{0,4},{32,4},{8192,4},{65536,4}};
    std::vector<u64> uploaded;
    tracker.ForEachUploadRanges(0,ranges,true,[&](u64 at,u64) { uploaded.push_back(at); },[&] {
        for(auto& region:tracker.regions) { assert(region.lock.held); assert(region.gpu.empty()); }
    });
    assert((uploaded == std::vector<u64>{0,8192,65536}));
    for(auto& region:tracker.regions) assert(!region.lock.held);
    assert(tracker.regions[0].gpu.size()==3 && tracker.regions[1].gpu.size()==1);
    assert(tracker.regions[0].cpu_pages.contains(1)); // gap stays CPU dirty
}
'''.replace('METHOD', method)
        with tempfile.TemporaryDirectory() as directory:
            exe = build(source, directory, 'page_locks')
            subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
