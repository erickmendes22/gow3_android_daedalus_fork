// SPDX-License-Identifier: GPL-2.0-or-later
// Android: AMD's PC FSR4 SDK is loaded through Windows DLLs.
// The Vulkan core and PC #308 depth/G-buffer optimization stay enabled.
// The caller already implements an FSR1/regular presentation fallback when
// Fsr4::Available()/Dispatch() return false. No Windows headers or DLLs.
#include "video_core/renderer_vulkan/vk_fsr4.h"

namespace Vulkan::Fsr4 {
bool Init(const Instance&) { return false; }
bool Available() { return false; }
const char* Name() { return "FSR4 unavailable on Android"; }
bool Dispatch(VkCommandBuffer, const Params&) { return false; }
} // namespace Vulkan::Fsr4
