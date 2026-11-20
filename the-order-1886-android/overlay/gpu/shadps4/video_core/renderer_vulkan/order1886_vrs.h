// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <atomic>

namespace Vulkan {

// Set after VkDevice creation, before any graphics pipeline is created.
// No VRS 4x4 path exists: only the extension-supported 2x2 or exact 1x1.
inline std::atomic_bool g_order1886_vrs_2x2_enabled{false};
// Counter is only incremented for actual eligible 2x2 draws, not for driver support.
inline std::atomic_uint64_t g_order1886_vrs_2x2_draws{0};
// Aggregated guard reasons: no per-draw logging or Vulkan timestamps.
inline std::atomic_uint64_t g_order1886_vrs_rejected_discard{0};
inline std::atomic_uint64_t g_order1886_vrs_rejected_coverage{0};
inline std::atomic_uint64_t g_order1886_vrs_rejected_side_effects{0};

} // namespace Vulkan
