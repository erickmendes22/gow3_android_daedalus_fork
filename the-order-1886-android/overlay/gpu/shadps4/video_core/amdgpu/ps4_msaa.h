// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <atomic>

namespace AmdGpu {
// The PC donor intentionally forces native PS4 MSAA. On Adreno 830, the Vulkan
// pipeline may be unable to bind mixed-sample color/depth attachments because
// VK_AMD_mixed_attachment_samples and VK_NV_framebuffer_mixed_samples are missing.
// The existing NumSamples() and Image::GetType() paths already implement a
// coherent single-sampled resource mode; allow that mode on Android.
inline std::atomic<bool> no_msaa{false};
inline bool NoMsaa() {
    return no_msaa.load(std::memory_order_relaxed);
}
} // namespace AmdGpu
