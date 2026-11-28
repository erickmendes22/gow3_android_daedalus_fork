// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>

namespace Gow3FexVa {
struct Mapping {
    std::uintptr_t address;
    int error;
    bool mapped;
};
struct Result {
    std::size_t bits = 0;
    unsigned relocated = 0;
};

// MAP_FIXED_NOREPLACE was introduced in Linux 4.17. Older kernels may
// ignore it and return another address. Only an exact mapping or EEXIST
// from a failed mapping proves the requested address is in range.
template<class Map, class Unmap>
Result Probe(std::size_t page_size, Map map, Unmap unmap) {
    Result out{};
    if (!page_size || (page_size & (page_size - 1)) || page_size > (1ULL << 30))
        return out;
    constexpr std::array<unsigned, 7> widths{57, 52, 48, 47, 42, 39, 36};
    for (const auto bits : widths) {
        const auto top = (std::uintptr_t{1} << bits) - page_size;
        // A second address in the upper half avoids falsely downgrading a
        // kernel whose topmost page is reserved by a guard or ABI rule.
        const auto middle = (std::uintptr_t{1} << (bits - 1)) + page_size;
        for (const auto requested : {top, middle}) {
            const auto r = map(requested, page_size);
            if (r.mapped) {
                unmap(r.address, page_size);
                if (r.address != requested) {
                    ++out.relocated;
                    continue;
                }
                out.bits = bits;
                return out;
            }
            if (r.error == EEXIST) {
                out.bits = bits;
                return out;
            }
        }
    }
    return out;
}
} // namespace Gow3FexVa
