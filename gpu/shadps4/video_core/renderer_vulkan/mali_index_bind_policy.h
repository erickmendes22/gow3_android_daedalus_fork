// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>
#include <limits>
namespace Vulkan {
struct MaliDirectIndexBind { std::uint64_t offset; std::uint32_t first_index; };
constexpr MaliDirectIndexBind CanonicalMaliDirectIndexBind(std::uint64_t offset,
    std::uint32_t element_size, std::uint32_t count, bool enabled) {
    if (!enabled || !count || (element_size != 2 && element_size != 4) ||
        offset % element_size != 0) return {offset, 0};
    const auto first = offset / element_size;
    if (first > std::numeric_limits<std::uint32_t>::max() - (count - 1u))
        return {offset, 0};
    return {0, static_cast<std::uint32_t>(first)};
}
}
