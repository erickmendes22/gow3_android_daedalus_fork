// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

namespace VideoCore {
// Vulkan read-after-read on the SAME VkImageLayout is not a dependency.
// A layout change, any source write or any destination write needs the
// original image barrier. Kept separate so the decision is C++-testable.
constexpr bool CanElideReadOnlyImageBarrier(bool enabled, bool same_layout,
                                            bool previous_writes, bool upcoming_writes) noexcept {
    return enabled && same_layout && !previous_writes && !upcoming_writes;
}
} // namespace VideoCore
