// SotC Android: conservative 64-word live CPU-dirty summary.
// Each bit says its associated 256 KiB word MIGHT have CPU-dirty pages.
// False positives cost only a normal scan; false negatives are forbidden.
// The existing RegionManager mutex serializes all bit changes.
#pragma once
#include <atomic>
#include <cstdint>

namespace SotcDirtyWord {
using U = std::uint64_t;
constexpr U Mask(unsigned first, unsigned last) noexcept {
    return (~U{0} << first) & (last == 63 ? ~U{0} : ((U{1} << (last + 1)) - 1));
}
inline bool MightContain(const std::atomic<U>& live, unsigned first, unsigned last) noexcept {
    return (live.load(std::memory_order_acquire) & Mask(first, last)) != 0;
}
inline void Update(std::atomic<U>& live, U active, U cleared) noexcept {
    // The caller already holds RegionManager's mutex. Clear expired words
    // before marking live ones, retaining every hot/grace page.
    if (cleared) live.fetch_and(~cleared, std::memory_order_release);
    if (active) live.fetch_or(active, std::memory_order_release);
}
} // namespace SotcDirtyWord
