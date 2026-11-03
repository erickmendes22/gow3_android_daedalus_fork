// SotC Android: lossless adjacent VkBufferCopy region coalescing.
// Maps the same source bytes to the same destination bytes, in the same order.
// Only merges neighboring regions within ONE GPU->CPU readback item.
#pragma once
#include <cstddef>
#include <cstdint>
#include <limits>

namespace SotcReadback {
template<class Copies>
std::size_t CoalesceAdjacent(Copies& copies) {
    const std::size_t original = copies.size();
    std::size_t kept = 0;
    for (std::size_t i = 0; i < original; ++i) {
        const auto current = copies[i];
        if (kept != 0) {
            auto& prior = copies[kept - 1];
            // Compare with subtraction to avoid overflowing offsets, and
            // never merge through staging alignment padding or guest gaps.
            if (current.srcOffset >= prior.srcOffset &&
                current.dstOffset >= prior.dstOffset &&
                current.srcOffset - prior.srcOffset == prior.size &&
                current.dstOffset - prior.dstOffset == prior.size &&
                prior.size <= std::numeric_limits<decltype(prior.size)>::max() - current.size) {
                prior.size += current.size;
                continue;
            }
        }
        if (kept != i) copies[kept] = current;
        ++kept;
    }
    copies.resize(kept);
    return original - kept;
}
} // namespace SotcReadback
