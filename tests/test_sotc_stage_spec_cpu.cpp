// SPDX-License-Identifier: GPL-2.0-or-later
// Self-contained native A/B invariant test for the SotC 0.1.29 CPU hot path.
// The full pinned renderer is separately patched and compiled in CI.
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>

struct RtKey {
    std::array<unsigned, 4> data{};
    bool operator==(const RtKey&) const = default;
};
struct BindKey {
    unsigned unified{}, buffer{};
    bool operator==(const BindKey&) const = default;
};
struct Memo {
    std::vector<unsigned> flat;
    RtKey rt{};
    BindKey bind{};
    std::uint64_t base{};
    std::size_t perm{}, count{};
    bool valid{};
    bool Matches(const std::vector<unsigned>& actual, RtKey r,
                 BindKey b, std::uint64_t p, std::size_t modules) const {
        return valid && count == modules && perm < modules &&
               base == p && rt == r && bind == b && flat == actual;
    }
};
int main() {
    constexpr std::size_t module_count = 3;
    Memo memo{{1,2,3,4,5,6}, RtKey{{1,9,2,7}}, BindKey{4,2},
              0x12345678ULL, 1, module_count, true};
    // Identical refreshed shader data => an existing module permutation.
    assert(memo.Matches({1,2,3,4,5,6}, RtKey{{1,9,2,7}},
                        BindKey{4,2}, 0x12345678ULL, module_count));
    // A single guest word modification must invalidate reuse.
    assert(!memo.Matches({1,2,3,4,5,7}, RtKey{{1,9,2,7}},
                         BindKey{4,2}, 0x12345678ULL, module_count));
    // Runtime specialization, binding offsets, code address and module list
    // are all distinct independent invalidation causes.
    assert(!memo.Matches({1,2,3,4,5,6}, RtKey{{1,9,2,8}},
                         BindKey{4,2}, 0x12345678ULL, module_count));
    assert(!memo.Matches({1,2,3,4,5,6}, RtKey{{1,9,2,7}},
                         BindKey{5,2}, 0x12345678ULL, module_count));
    assert(!memo.Matches({1,2,3,4,5,6}, RtKey{{1,9,2,7}},
                         BindKey{4,2}, 0x12345679ULL, module_count));
    assert(!memo.Matches({1,2,3,4,5,6}, RtKey{{1,9,2,7}},
                         BindKey{4,2}, 0x12345678ULL, module_count+1));
    memo.valid = false; // after shader binary replace or async insertion
    assert(!memo.Matches({1,2,3,4,5,6}, RtKey{{1,9,2,7}},
                         BindKey{4,2}, 0x12345678ULL, module_count));

    // Exact per-command-buffer ownership transfer: the consumer receives the
    // original bytes without a second copy; the producer retains its buffer
    // and can safely reuse it only after the consumer finishes.
    std::vector<unsigned> cp_snapshot{10,20,30,40};
    std::vector<unsigned> draw_state{111,222,333};
    auto* original_cp_storage = cp_snapshot.data();
    draw_state.swap(cp_snapshot);
    assert(draw_state.data() == original_cp_storage);
    assert((draw_state == std::vector<unsigned>{10,20,30,40}));
    assert((cp_snapshot == std::vector<unsigned>{111,222,333}));
    cp_snapshot.assign({9,8,7,6});
    assert((draw_state == std::vector<unsigned>{10,20,30,40}));
    draw_state.swap(cp_snapshot);
    assert((draw_state == std::vector<unsigned>{9,8,7,6}));
    assert((cp_snapshot == std::vector<unsigned>{10,20,30,40}));
    return 0;
}
