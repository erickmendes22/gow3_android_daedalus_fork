// SPDX-FileCopyrightText: Copyright 2026 Daedalus fork contributors
// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

// Shadow of the Colossus precise async-readback fast path.
// Only a fully covered byte range may share an existing in-flight readback.
// Partial overlaps still take the original path; no guest bytes are skipped.
// Header is independent of Vulkan and can be compiled in a host unit test.
#include <algorithm>
#include <cstdint>
#include <limits>

namespace SotcReadbackDedup {
template<class ReadbackItems>
[[nodiscard]] bool Covers(const ReadbackItems& pending, std::uint64_t addr,
                          std::uint64_t bytes) {
    if (bytes == 0 || bytes > std::numeric_limits<std::uint64_t>::max() - addr) {
        return false;
    }
    const std::uint64_t end = addr + bytes;
    std::uint64_t covered = addr;
    while (covered < end) {
        std::uint64_t next = covered;
        for (const auto& item : pending) {
            if (!item.arena) {
                continue;
            }
            for (const auto& copy : item.copies) {
                const std::uint64_t base = item.arena->cpu_addr;
                if (copy.srcOffset > std::numeric_limits<std::uint64_t>::max() - base) {
                    continue;
                }
                const std::uint64_t first = base + copy.srcOffset;
                if (copy.size > std::numeric_limits<std::uint64_t>::max() - first) {
                    continue;
                }
                const std::uint64_t last = first + copy.size;
                if (first <= covered && covered < last) {
                    next = std::max(next, last);
                }
            }
        }
        if (next == covered) {
            return false; // includes gaps and never-copied guest bytes
        }
        covered = next;
    }
    return true;
}
} // namespace SotcReadbackDedup
