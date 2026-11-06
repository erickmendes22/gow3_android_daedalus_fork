// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>

namespace VideoCore {

// This is MEMORY reuse, not an image/view/guest-format alias. Only GPU-retired
// allocations may be considered, and the old VkImage is destroyed before
// the new VkImage is bound. The candidate must be a non-dedicated suballocation
// with the same memory type and sufficient size/alignment for the new image.
constexpr bool CanRebindRetiredImageMemory(
    std::uint64_t requested_size, std::uint64_t required_alignment,
    std::uint32_t supported_memory_types, bool requires_dedicated,
    std::uint64_t allocation_size, std::uint64_t allocation_offset,
    std::uint32_t allocation_memory_type, bool allocated_dedicated) {
    if (!requested_size || !required_alignment || requires_dedicated ||
        allocated_dedicated || allocation_memory_type >= 32)
        return false;
    if (!(supported_memory_types & (1u << allocation_memory_type)) ||
        allocation_offset % required_alignment != 0 ||
        allocation_size < requested_size)
        return false;
    // Avoid retaining an oversized allocation for a tiny image. This is a
    // bounded resource-budget decision, not a guess about driver performance.
    const auto max_waste = requested_size / 4;
    return allocation_size - requested_size <= max_waste;
}

} // namespace VideoCore
