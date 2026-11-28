#pragma once
#include <algorithm>
#include <cstdint>
#include <limits>

namespace VideoCore {
// The caller supplies the actual owning VkBuffer, not the nominal VA page.
// Zero means invalid input, never an instruction to skip resident data.
constexpr std::uint32_t DmaArenaChunk(std::uint64_t addr, std::uint64_t end,
                                     std::uint64_t base, std::uint64_t capacity,
                                     std::uint64_t block_size) {
    if (!block_size || (block_size & (block_size-1)) || addr >= end ||
        addr < base || addr-base >= capacity) return 0;
    const auto remaining = std::min(end-addr, capacity-(addr-base));
    const auto limit = std::uint64_t{std::numeric_limits<std::uint32_t>::max()} & ~(block_size-1);
    const auto bytes = std::min(remaining, limit);
    return bytes % block_size ? 0 : static_cast<std::uint32_t>(bytes);
}
}
