// SPDX-License-Identifier: GPL-2.0-or-later
#include "fex_android_va_probe.h"
#include <cassert>
using Gow3FexVa::Mapping;
int main() {
    constexpr std::size_t page = 4096;
    unsigned maps = 0, unmaps = 0;
    auto unmap = [&](std::uintptr_t, std::size_t n) { assert(n == page); ++unmaps; };
    // Legacy 39-bit Android: ignored NOREPLACE and a relocated success,
    // even with stale EEXIST. Every temporary mapping must be unmapped.
    auto legacy = Gow3FexVa::Probe(page, [&](std::uintptr_t a, std::size_t) {
        ++maps;
        return Mapping{a < (1ULL << 39) ? a : 0x7000000000ULL, EEXIST, true};
    }, unmap);
    assert(legacy.bits == 39 && legacy.relocated == 10 && maps == 11 && unmaps == maps);
    maps = unmaps = 0;
    auto modern = Gow3FexVa::Probe(page, [&](std::uintptr_t a, std::size_t) {
        ++maps;
        return a < (1ULL << 48) ? Mapping{a, 0, true} : Mapping{0, ENOMEM, false};
    }, unmap);
    assert(modern.bits == 48 && modern.relocated == 0 && maps == 5 && unmaps == 1);
    auto occupied = Gow3FexVa::Probe(page, [](std::uintptr_t a, std::size_t) {
        return Mapping{0, a < (1ULL << 42) ? EEXIST : ENOMEM, false};
    }, [](auto, auto) { assert(false); });
    assert(occupied.bits == 42);
    auto guarded = Gow3FexVa::Probe(16384, [](std::uintptr_t a, std::size_t n) {
        assert(n == 16384 && a % n == 0);
        return a < (1ULL << 39) - n ? Mapping{a, 0, true} : Mapping{0, ENOMEM, false};
    }, [](auto, auto n) { assert(n == 16384); });
    assert(guarded.bits == 39);
    auto fail = Gow3FexVa::Probe(page, [](auto, auto) { return Mapping{0, EPERM, false}; }, [](auto, auto) {});
    assert(!fail.bits);
    auto invalid = Gow3FexVa::Probe(123, [](auto, auto) { assert(false); return Mapping{}; }, [](auto, auto) {});
    assert(!invalid.bits);
}
