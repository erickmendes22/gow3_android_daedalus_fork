// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
namespace VideoCore {
// Slot zero is the counter, not an address. Atomic increments may exceed
// the number of slots under a burst of GPU faults.
constexpr std::uint32_t FaultResultCount(std::uint64_t reported, std::size_t slots) {
    if (slots <= 1) return 0;
    return static_cast<std::uint32_t>(reported < slots ? reported : slots - 1);
}
}
