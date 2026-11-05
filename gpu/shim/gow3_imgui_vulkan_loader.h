// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <vulkan/vulkan.h>

namespace Gow3Overlay {
// Adapted from Bloodborne-Android bbport_overlay.cpp, commit
// 2e4726530b04f76e513e232d272d386e9973c73b. AHB presentation does not
// enable Vulkan surface/swapchain extensions. ImGui loads its unused window
// helpers too; rejecting those leaves later, required render functions null.
inline bool IsUnusedWsiFunction(const char* name) {
    for (const char* unused : {"vkCreateSwapchainKHR", "vkDestroySurfaceKHR",
            "vkDestroySwapchainKHR", "vkGetPhysicalDeviceSurfaceCapabilitiesKHR",
            "vkGetPhysicalDeviceSurfaceFormatsKHR", "vkGetPhysicalDeviceSurfacePresentModesKHR",
            "vkGetSwapchainImagesKHR"}) {
        if (std::strcmp(name, unused) == 0) return true;
    }
    return false;
}

[[noreturn]] inline void UnusedWsiFunction() {
    std::fputs("Overlay: Vulkan WSI helper called during AHB presentation\n", stderr);
    std::abort();
}

inline PFN_vkVoidFunction ResolveImGuiFunction(PFN_vkGetInstanceProcAddr gipa,
                                              VkInstance instance, const char* name, bool ahb) {
    const auto function = gipa(instance, name);
    if (function) return function;
    if (ahb && IsUnusedWsiFunction(name)) {
        return reinterpret_cast<PFN_vkVoidFunction>(&UnusedWsiFunction);
    }
    std::fprintf(stderr, "Overlay: required Vulkan function missing: %s\n", name);
    return nullptr;
}
} // namespace Gow3Overlay
