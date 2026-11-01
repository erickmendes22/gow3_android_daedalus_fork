// Adapted from ducvd89/Bloodborne-Android, commit 2e4726530b04f76e513e232d272d386e9973c73b.
// Original implementation: gpu/shim/vk_driver_loader.{cpp,h}. See docs/BIONIC_EXPERIMENT.md.
// order1886: the one place that loads a Vulkan driver (see vk_driver_loader.cpp).
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*Order1886VkVoidFunction)(void);
typedef Order1886VkVoidFunction (*Order1886VkGetInstanceProcAddr)(void* instance, const char* name);

/// Loads the Vulkan driver once (ORDER1886_VULKAN_DRIVER unset: the system loader's libvulkan.so; set to a
/// path: that driver library directly) and returns its vkGetInstanceProcAddr, or NULL (logged).
/// Every other Vulkan function of the process is resolved through it.
Order1886VkGetInstanceProcAddr order1886_vk_get_instance_proc_addr(void);

#ifdef __cplusplus
}
#endif
