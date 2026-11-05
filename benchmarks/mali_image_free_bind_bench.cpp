// Synthetic CPU-only A/B screen for the image-free BindTextures branch.
// Does not pretend to execute Vulkan, guest FEX or PanVK driver code.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <numeric>
#include <vector>

#if defined(__GNUC__)
#define NOINLINE __attribute__((noinline))
#else
#define NOINLINE
#endif

struct Stage {
    std::array<std::uint64_t, 4> samplers{13, 17, 19, 23};
    std::size_t num_images = 0;
    std::size_t num_samplers = 2;
};
struct Scratch {
    std::vector<std::uint64_t> image_bindings, image_entries, image_desc_overflow, image_desc_storage;
    std::uint64_t bind_epoch = 0;
    std::uint64_t sink = 0;
};

NOINLINE void BindSamplers(Scratch& scratch, const Stage& stage) {
    for (std::size_t i = 0; i < stage.num_samplers; ++i) {
        scratch.sink += stage.samplers[i];
    }
}

// Model the specific empty-image bookkeeping which old BindTextures performs.
// Its *full* production function has many additional paths not benchmarked here.
NOINLINE void OldImageFreeBind(Scratch& s, const Stage& stage) {
    const auto first_image_idx = s.image_bindings.size();
    s.image_bindings.clear();
    s.image_entries.clear();
    s.image_desc_overflow.clear();
    s.image_desc_storage.clear();
    ++s.bind_epoch;
    std::array<std::uint64_t, 16> resolved{};
    // A normally empty texture loop; black box keeps the set bookkeeping live.
    s.sink += (resolved[0] + (first_image_idx & 0));
    for (std::size_t i = 0; i < stage.num_images; ++i) {
        s.sink += i + 1;
    }
    BindSamplers(s, stage);
}
NOINLINE void NewImageFreeBind(Scratch& s, const Stage& stage) {
    if (stage.num_images == 0) {
        BindSamplers(s, stage);
        return;
    }
    OldImageFreeBind(s, stage);
}

using Clock = std::chrono::steady_clock;
using Fn = void(*)(Scratch&, const Stage&);
NOINLINE double Measure(Fn fn, Scratch& s, Stage& st, int iterations) {
    const auto start = Clock::now();
    for (int i = 0; i < iterations; ++i) {
        fn(s, st);
    }
    const auto end = Clock::now();
    return std::chrono::duration<double, std::nano>(end-start).count() / iterations;
}
static double Median(std::vector<double> a) {
    std::sort(a.begin(), a.end());
    return a[a.size()/2];
}

int main(int argc, char** argv) {
    const int iterations = argc > 1 ? std::atoi(argv[1]) : 1000000;
    if (iterations < 10000) return 2;
    Stage stage;
    Scratch baseline, candidate;
    // Run each mode before measuring; alternate order against drift.
    Measure(&OldImageFreeBind, baseline, stage, iterations/4);
    Measure(&NewImageFreeBind, candidate, stage, iterations/4);
    std::vector<double> a, b;
    for (int round = 0; round < 11; ++round) {
        if ((round & 1) == 0) {
            a.push_back(Measure(&OldImageFreeBind, baseline, stage, iterations));
            b.push_back(Measure(&NewImageFreeBind, candidate, stage, iterations));
        } else {
            b.push_back(Measure(&NewImageFreeBind, candidate, stage, iterations));
            a.push_back(Measure(&OldImageFreeBind, baseline, stage, iterations));
        }
    }
    if (baseline.sink == 0 || candidate.sink == 0) return 3;
    std::cout << "{\"kind\":\"synthetic_image_free_bind_only\","
              << "\"iterations\":" << iterations << ",\"samples\":11,"
              << "\"baseline_ns_per_draw\":" << Median(a) << ","
              << "\"candidate_ns_per_draw\":" << Median(b) << ","
              << "\"delta_ns_per_draw\":" << Median(a)-Median(b) << ","
              << "\"method\":\"microbenchmark_model_not_vulkan_or_fex\"}"
              << std::endl;
}
