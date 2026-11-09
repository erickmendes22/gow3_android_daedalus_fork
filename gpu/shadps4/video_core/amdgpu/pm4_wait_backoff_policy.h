// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>
namespace AmdGpu {
// Scheduler policy only. WAIT_REG_MEM predicates, queue ordering and fences
// remain unchanged. batch=1 is original sleep-on-every-blocked-resume.
constexpr bool SleepOnBlockedPm4Resume(std::uint32_t consecutive, std::uint32_t batch) noexcept {
    return batch <= 1 || consecutive % batch == 0;
}
static_assert(SleepOnBlockedPm4Resume(1, 1));
static_assert(!SleepOnBlockedPm4Resume(1, 8));
static_assert(!SleepOnBlockedPm4Resume(7, 8));
static_assert(SleepOnBlockedPm4Resume(8, 8));
static_assert(SleepOnBlockedPm4Resume(16, 8));
} // namespace AmdGpu
