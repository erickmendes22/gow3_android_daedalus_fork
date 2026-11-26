// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>
#include <limits>
namespace VideoCore {
// Exact adjacency in both address spaces; no sorting, holes, overlap or
// padding expansion. The CPU publication loop uses the same merged regions.
template<class Copy>
constexpr bool MergeAdjacentCopy(Copy& a, const Copy& b) {
    constexpr auto max = std::numeric_limits<std::uint64_t>::max();
    if (!a.size || !b.size || a.srcOffset > max-a.size || a.dstOffset > max-a.size ||
        a.size > max-b.size || a.srcOffset+a.size != b.srcOffset ||
        a.dstOffset+a.size != b.dstOffset || b.srcOffset > max-b.size ||
        b.dstOffset > max-b.size) return false;
    a.size += b.size;
    return true;
}
template<class Container>
std::size_t CoalesceAdjacentCopies(Container& copies) {
    std::size_t out = 0;
    for (std::size_t i=0; i<copies.size(); ++i) {
        if (out && MergeAdjacentCopy(copies[out-1], copies[i])) continue;
        if (i != out) copies[out] = copies[i];
        ++out;
    }
    const auto saved = copies.size()-out;
    copies.resize(out);
    return saved;
}
}
