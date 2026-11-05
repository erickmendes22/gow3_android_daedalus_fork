// Execute the real ImGui backend loader with a driver that has no WSI extensions.
#include <cassert>
#include <cstring>
#include "gow3_imgui_vulkan_loader.h"
#include "imgui_impl_vulkan.h"

static bool omit_required;
static bool reached_physical_properties;
static void Stub() {}
static PFN_vkVoidFunction Driver(VkInstance, const char* name) {
    if (Gow3Overlay::IsUnusedWsiFunction(name)) return nullptr;
    if (omit_required && !std::strcmp(name,"vkCreateShaderModule")) return nullptr;
    if (!std::strcmp(name,"vkGetPhysicalDeviceProperties")) reached_physical_properties=true;
    return &Stub;
}
static PFN_vkVoidFunction RawLoader(const char* name, void*) { return Driver({},name); }
static PFN_vkVoidFunction AhbLoader(const char* name, void*) {
    return Gow3Overlay::ResolveImGuiFunction(&Driver,{},name,true);
}
int main() {
    // Reproduce the shipped APK: WSI lookup aborts loading before this core function.
    assert(!ImGui_ImplVulkan_LoadFunctions(VK_API_VERSION_1_3,&RawLoader));
    assert(!reached_physical_properties);
    // AHB must finish loading all actual render functions without enabling WSI.
    assert(ImGui_ImplVulkan_LoadFunctions(VK_API_VERSION_1_3,&AhbLoader));
    assert(reached_physical_properties);
    assert(Gow3Overlay::ResolveImGuiFunction(&Driver,{},"vkCreateSwapchainKHR",true));
    // Ordinary desktop presentation still requires its real swapchain entry point.
    assert(!Gow3Overlay::ResolveImGuiFunction(&Driver,{},"vkCreateSwapchainKHR",false));
    // Missing render functions cannot be replaced by an unused-helper placeholder.
    omit_required=true;
    assert(!ImGui_ImplVulkan_LoadFunctions(VK_API_VERSION_1_3,&AhbLoader));
}
