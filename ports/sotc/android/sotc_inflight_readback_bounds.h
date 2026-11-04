// SotC Android: lossless overlap filtering for active GPU -> guest readbacks.
// A span rejected by this predicate cannot overlap. In-flight readbacks retain
// their original GPU copy, wait, cache invalidation, and host-memory application.
#pragma once
#include <cstdint>

namespace SotcInflight {
constexpr bool Overlaps(std::uint64_t addr, std::uint64_t bytes,
                        std::uint64_t other, std::uint64_t other_bytes) noexcept {
    if (bytes == 0 || other_bytes == 0) return false;
    // Compare differences rather than sums: cannot overflow guest addresses.
    return addr <= other ? other - addr < bytes : addr - other < other_bytes;
}
} // namespace SotcInflight
