// Android/Bionic driver bring-up. No libvulkan link and no game-specific patches.
#define VK_NO_PROTOTYPES
#ifdef __ANDROID__
#define VK_USE_PLATFORM_ANDROID_KHR
#include <android/hardware_buffer.h>
#endif
#include <vulkan/vulkan.h>
#include "vk_driver_loader.h"
#include <cstdio>
#include <cstring>
#include <vector>

int main() {
    auto gipa = reinterpret_cast<PFN_vkGetInstanceProcAddr>(gow3_vk_get_instance_proc_addr());
    if (!gipa) return 1; // dlerror includes missing Android dependencies / namespace failures.
    auto create = reinterpret_cast<PFN_vkCreateInstance>(gipa(nullptr, "vkCreateInstance"));
    if (!create) { std::fprintf(stderr, "Missing vkCreateInstance\n"); return 1; }
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "Daedalus Bionic driver check";
    app.apiVersion = VK_API_VERSION_1_1;
    VkInstanceCreateInfo ci{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    ci.pApplicationInfo = &app;
    VkInstance instance{};
    VkResult result = create(&ci, nullptr, &instance);
    if (result != VK_SUCCESS) { std::fprintf(stderr, "vkCreateInstance: %d\n", result); return 1; }
#define INSTANCE_FN(name) auto name = reinterpret_cast<PFN_##name>(gipa(instance, #name)); \
    if (!name) { std::fprintf(stderr, "Missing %s\n", #name); return 1; }
    INSTANCE_FN(vkDestroyInstance)
    INSTANCE_FN(vkEnumeratePhysicalDevices)
    INSTANCE_FN(vkGetPhysicalDeviceProperties)
    INSTANCE_FN(vkEnumerateDeviceExtensionProperties)
    INSTANCE_FN(vkGetPhysicalDeviceQueueFamilyProperties)
    INSTANCE_FN(vkGetPhysicalDeviceExternalSemaphoreProperties)
    INSTANCE_FN(vkCreateDevice)
    INSTANCE_FN(vkGetDeviceProcAddr)
    uint32_t count = 0;
    result = vkEnumeratePhysicalDevices(instance, &count, nullptr);
    if (result != VK_SUCCESS || !count) {
        std::fprintf(stderr, "No Vulkan physical device: %d\n", result);
        vkDestroyInstance(instance, nullptr); return 1;
    }
    std::vector<VkPhysicalDevice> devices(count);
    result = vkEnumeratePhysicalDevices(instance, &count, devices.data());
    if (result != VK_SUCCESS) { vkDestroyInstance(instance, nullptr); return 1; }
    bool passed = false;
    for (auto physical : devices) {
        VkPhysicalDeviceProperties props{};
        vkGetPhysicalDeviceProperties(physical, &props);
        std::printf("GPU: %s; vendor=0x%x device=0x%x; Vulkan %u.%u.%u\n", props.deviceName,
                    props.vendorID, props.deviceID, VK_API_VERSION_MAJOR(props.apiVersion),
                    VK_API_VERSION_MINOR(props.apiVersion), VK_API_VERSION_PATCH(props.apiVersion));
        uint32_t n = 0;
        if (vkEnumerateDeviceExtensionProperties(physical, nullptr, &n, nullptr) != VK_SUCCESS) continue;
        std::vector<VkExtensionProperties> ext(n);
        if (vkEnumerateDeviceExtensionProperties(physical, nullptr, &n, ext.data()) != VK_SUCCESS) continue;
        const char* required[] = {"VK_ANDROID_external_memory_android_hardware_buffer",
                                  "VK_KHR_external_semaphore_fd", "VK_EXT_queue_family_foreign"};
        bool compatible = true;
        for (const char* name : required) {
            bool found = false;
            for (const auto& e : ext) found |= std::strcmp(e.extensionName, name) == 0;
            std::printf("%s: %s\n", name, found ? "yes" : "MISSING");
            compatible &= found;
        }
        VkPhysicalDeviceExternalSemaphoreInfo info{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_SEMAPHORE_INFO};
        info.handleType = VK_EXTERNAL_SEMAPHORE_HANDLE_TYPE_SYNC_FD_BIT;
        VkExternalSemaphoreProperties sem{VK_STRUCTURE_TYPE_EXTERNAL_SEMAPHORE_PROPERTIES};
        vkGetPhysicalDeviceExternalSemaphoreProperties(physical, &info, &sem);
        auto flags = VK_EXTERNAL_SEMAPHORE_FEATURE_EXPORTABLE_BIT | VK_EXTERNAL_SEMAPHORE_FEATURE_IMPORTABLE_BIT;
        compatible &= (sem.externalSemaphoreFeatures & flags) == static_cast<VkExternalSemaphoreFeatureFlags>(flags);
        std::printf("SYNC_FD import/export: 0x%x\n", sem.externalSemaphoreFeatures);
        if (!compatible) continue;
        uint32_t nq = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &nq, nullptr);
        std::vector<VkQueueFamilyProperties> queues(nq);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &nq, queues.data());
        uint32_t family = 0;
        while (family < nq && !(queues[family].queueFlags & VK_QUEUE_GRAPHICS_BIT)) ++family;
        if (family == nq) continue;
        float priority = 1;
        VkDeviceQueueCreateInfo q{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        q.queueFamilyIndex = family; q.queueCount = 1; q.pQueuePriorities = &priority;
        VkDeviceCreateInfo dc{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
        dc.queueCreateInfoCount = 1; dc.pQueueCreateInfos = &q;
        dc.enabledExtensionCount = 3; dc.ppEnabledExtensionNames = required;
        VkDevice device{};
        result = vkCreateDevice(physical, &dc, nullptr, &device);
        std::printf("vkCreateDevice: %d\n", result);
        if (result != VK_SUCCESS) continue;
        auto destroy = reinterpret_cast<PFN_vkDestroyDevice>(vkGetDeviceProcAddr(device, "vkDestroyDevice"));
        bool entrypoints = destroy && vkGetDeviceProcAddr(device, "vkGetAndroidHardwareBufferPropertiesANDROID") &&
                           vkGetDeviceProcAddr(device, "vkGetMemoryAndroidHardwareBufferANDROID") &&
                           vkGetDeviceProcAddr(device, "vkImportSemaphoreFdKHR") &&
                           vkGetDeviceProcAddr(device, "vkGetSemaphoreFdKHR");
        std::printf("AHB and sync-fd device entry points: %s\n", entrypoints ? "yes" : "MISSING");
        passed |= entrypoints;
        if (destroy) destroy(device, nullptr);
    }
    vkDestroyInstance(instance, nullptr);
    std::printf("Bionic presentation prerequisites: %s (does not test game rendering)\n", passed ? "PASS" : "FAIL");
    return passed ? 0 : 1;
}
