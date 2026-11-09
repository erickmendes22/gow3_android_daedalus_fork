// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>
#include <cstddef>

namespace VideoCore {

// Keep at least one retired VkImage per distinct ETC2 description; a memory
// rebind would destroy that image despite no pool trim or memory pressure.
constexpr bool ProtectLastRetiredEtc2(std::size_t identical_retired_entries) {
    return identical_retired_entries <= 1;
}
static_assert(ProtectLastRetiredEtc2(1));
static_assert(!ProtectLastRetiredEtc2(2));

// This is MEMORY reuse, not an image/view/guest-format alias. Only GPU-retired
// allocations may be considered, and the old VkImage is destroyed before
// the new VkImage is bound. The candidate must be a non-dedicated suballocation
// with the same memory type and sufficient size/alignment for the new image.
constexpr bool CanRebindRetiredImageMemory(
    std::uint64_t requested_size, std::uint64_t required_alignment,
    std::uint32_t supported_memory_types, bool requires_dedicated,
    std::uint64_t allocation_size, std::uint64_t allocation_offset,
    std::uint32_t allocation_memory_type, bool allocated_dedicated,
    bool bounded_etc2_slack = false) {
    if (!requested_size || !required_alignment || requires_dedicated ||
        allocated_dedicated || allocation_memory_type >= 32)
        return false;
    if (!(supported_memory_types & (1u << allocation_memory_type)) ||
        allocation_offset % required_alignment != 0 ||
        allocation_size < requested_size)
        return false;
    // The normal RGBA/BC path retains the strict 25% limit.
    // ETC2 compressed images on Mali can reuse a *completed* allocation
    // from a different texture shape with up to 100% size slack, capped at
    // 8 MiB absolute waste. This avoids an expensive fresh VMA allocation
    // when an already-idle compatible block is available. No extra memory
    // is reserved, and the VMA memory-type/alignment/dedication rules above
    // remain mandatory. The original pixels are never reused in this path.
    const auto max_waste = bounded_etc2_slack
        ? (requested_size < (8ull << 20) ? requested_size : (8ull << 20))
        : requested_size / 4;
    return allocation_size - requested_size <= max_waste;
}

} // namespace VideoCore
