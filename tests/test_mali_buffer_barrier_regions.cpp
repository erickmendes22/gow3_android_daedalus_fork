// Host tests: exact hazard-union coverage and synthetic overhead; this does
// NOT measure PanVK GPU waits or game FPS.
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>
#include "video_core/renderer_vulkan/vk_mali_buffer_barrier_regions.h"

using Vulkan::MaliBufferBarrierRegions;
using u64 = std::uint64_t;

static bool Covered(const MaliBufferBarrierRegions& r, u64 buffer, u64 byte) {
    for (size_t i = 0; i < r.Count(); ++i) {
        const auto& e = r[i];
        if (e.buffer == buffer && byte >= e.offset && byte < e.offset + e.size)
            return true;
    }
    return false;
}

int main() {
    MaliBufferBarrierRegions r;
    assert(r.Add(1, 0, 8));
    assert(r.Add(1, 16, 8));
    assert(r.Add(1, 8, 8)); // bridges both existing intervals
    assert(r.Count() == 1 && Covered(r, 1, 0) && Covered(r, 1, 23));
    assert(!Covered(r, 1, 24));
    assert(r.Add(2, 8, 4));
    assert(r.Count() == 2 && Covered(r, 2, 8) && !Covered(r, 1, 24));
    r.Clear();

    // A write to buffer B can precede a hazard on buffer A. FlushBarriers
    // retires its entire tracker, not just A. The scoped barriers must
    // therefore include B too, even if B was not the immediate hazard.
    r.Clear();
    assert(r.Add(1, 0, 64));   // earlier WRITE A
    assert(r.Add(2, 512, 64)); // earlier WRITE B, no hazard yet
    assert(r.Add(1, 0, 64));   // later READ A causes flush
    assert(Covered(r, 2, 512) && Covered(r, 2, 575));
    // A draw with >8 disjoint buffers MUST instead use the global barrier.
    r.Clear();
    for (u64 id = 1; id <= MaliBufferBarrierRegions::Max + 1; ++id) {
        r.Add(id, 0, 4);
    }
    assert(r.Overflow());
    r.Clear();

    // Every inserted hazard byte is either covered by an exact VkBuffer range
    // or causes a safe global fallback. Test randomized overlaps and aliases.
    std::mt19937_64 gen(0x720u);
    size_t safe_replays = 0, overflow_replays = 0;
    for (int trial = 0; trial < 10000; ++trial) {
        r.Clear();
        std::array<std::array<bool, 512>, 5> written{};
        const int n = 1 + (gen() % 24);
        for (int i = 0; i < n; ++i) {
            const u64 buffer = 1 + (gen() % 5);
            const u64 begin = gen() % 496;
            const u64 count = 1 + (gen() % 16);
            for (u64 b = begin; b < begin + count; ++b) written[buffer-1][b] = true;
            r.Add(buffer, begin, count);
        }
        if (r.Overflow()) {
            ++overflow_replays;
            continue; // runtime chooses original global barrier
        }
        ++safe_replays;
        for (u64 buffer = 1; buffer <= 5; ++buffer)
            for (u64 b = 0; b < 512; ++b)
                if (written[buffer-1][b]) assert(Covered(r, buffer, b));
    }
    assert(safe_replays > 0 && overflow_replays > 0);
    r.Clear();
    assert(!r.Add(1, ~u64{0} - 1, 3) && r.Overflow());
    r.Clear();
    assert(!r.Add(0, 0, 5) && r.Overflow());

    // CPU microbenchmark of the *actual* region code, not shader/GPU time.
    constexpr unsigned batches = 400000;
    const auto begin = std::chrono::steady_clock::now();
    u64 seed = 0x7206ab54e11c031dull;
    size_t sink = 0;
    for (unsigned i = 0; i < batches; ++i) {
        r.Clear();
        for (u64 k = 1; k <= 4; ++k) {
            // Dynamic, data-dependent non-constant hazard ranges: without this
            // the optimizer reduced the earlier synthetic loop to a constant,
            // reporting an impossible 9 ns for four real hazard insertions.
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            const u64 buffer = 1 + (seed & 7);
            const u64 offset = (seed >> 3) & 0x3FFF;
            sink += r.Add(buffer, offset, 32);
            sink += r.Count() ^ r[0].offset;
        }
    }
    const auto end = std::chrono::steady_clock::now();
    const double us = std::chrono::duration<double, std::micro>(end-begin).count() / batches;
    assert(sink != 0 && seed != 0);
    std::printf("GOW3_MALI_LOCAL_BARRIER_SYNTH safe=%zu overflow=%zu 4hazards_us=%.3f "
                "scope_bytes=128 vs whole-buffer-model=268435456 "
                "WARNING=host-CPU-NOT-Mali-GPU-FPS\\n",
                safe_replays, overflow_replays, us);
    return 0;
}
