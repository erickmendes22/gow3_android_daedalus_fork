// GoW3 Mali: native Vulkan (host driver) cache lifecycle experiment.
// This is NOT a Mali/PanVK FPS benchmark. It validates that using a distinct
// worker VkPipelineCache, merging after join, serializing and restoring work.
#include <vulkan/vulkan.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <future>
#include <stdexcept>
#include <vector>

#define CHECK_VK(call) do { \
    const VkResult r = (call); \
    if (r != VK_SUCCESS) { \
        std::fprintf(stderr, "Vulkan failure %s: %d\n", #call, int(r)); \
        std::exit(3); \
    } \
} while (0)

constexpr std::uint32_t code[] = {
    0x7230203, 0x10000, 0x8000b, 0xa, 0x0, 0x20011, 0x1, 0x6000b, 0x1,
    0x4c534c47, 0x6474732e, 0x3035342e, 0x0, 0x3000e, 0x0, 0x1, 0x5000f,
    0x5, 0x4, 0x6e69616d, 0x0, 0x60010, 0x4, 0x11, 0x1, 0x1, 0x1, 0x30003,
    0x2, 0x1c2, 0x40005, 0x4, 0x6e69616d, 0x0, 0x40047, 0x9, 0xb, 0x19,
    0x20013, 0x2, 0x30021, 0x3, 0x2, 0x40015, 0x6, 0x20, 0x0, 0x40017,
    0x7, 0x6, 0x3, 0x4002b, 0x6, 0x8, 0x1, 0x6002c, 0x7, 0x9, 0x8, 0x8,
    0x8, 0x50036, 0x2, 0x4, 0x0, 0x3, 0x200f8, 0x5, 0x100fd, 0x10038,
};

using Clock = std::chrono::steady_clock;
using Nanoseconds = std::chrono::nanoseconds;

struct Device {
    VkInstance instance = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    VkShaderModule shader = VK_NULL_HANDLE;
    VkPipelineLayout layout = VK_NULL_HANDLE;
    VkComputePipelineCreateInfo ci{};
    char name[VK_MAX_PHYSICAL_DEVICE_NAME_SIZE]{};

    Device() {
        VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
        CHECK_VK(vkCreateInstance(&ici, nullptr, &instance));
        std::uint32_t count = 0;
        CHECK_VK(vkEnumeratePhysicalDevices(instance, &count, nullptr));
        if (count == 0) throw std::runtime_error("No Vulkan physical device on host");
        std::vector<VkPhysicalDevice> physicals(count);
        CHECK_VK(vkEnumeratePhysicalDevices(instance, &count, physicals.data()));
        std::uint32_t family = UINT32_MAX;
        for (auto p : physicals) {
            std::uint32_t n = 0;
            vkGetPhysicalDeviceQueueFamilyProperties(p, &n, nullptr);
            std::vector<VkQueueFamilyProperties> props(n);
            vkGetPhysicalDeviceQueueFamilyProperties(p, &n, props.data());
            for (std::uint32_t i = 0; i < n; ++i) {
                if (props[i].queueCount && (props[i].queueFlags & VK_QUEUE_COMPUTE_BIT)) {
                    physical = p;
                    family = i;
                    break;
                }
            }
            if (physical) break;
        }
        if (!physical) throw std::runtime_error("No Vulkan compute queue");
        VkPhysicalDeviceProperties props{};
        vkGetPhysicalDeviceProperties(physical, &props);
        std::strncpy(name, props.deviceName, sizeof(name) - 1);
        const float priority = 1.0f;
        VkDeviceQueueCreateInfo qi{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        qi.queueFamilyIndex = family;
        qi.queueCount = 1;
        qi.pQueuePriorities = &priority;
        VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
        dci.queueCreateInfoCount = 1;
        dci.pQueueCreateInfos = &qi;
        CHECK_VK(vkCreateDevice(physical, &dci, nullptr, &device));
        VkShaderModuleCreateInfo sci{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        sci.codeSize = sizeof(code);
        sci.pCode = code;
        CHECK_VK(vkCreateShaderModule(device, &sci, nullptr, &shader));
        VkPipelineLayoutCreateInfo lci{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
        CHECK_VK(vkCreatePipelineLayout(device, &lci, nullptr, &layout));
        ci = {VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
        ci.stage = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO};
        ci.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        ci.stage.module = shader;
        ci.stage.pName = "main";
        ci.layout = layout;
    }

    ~Device() {
        if (layout) vkDestroyPipelineLayout(device, layout, nullptr);
        if (shader) vkDestroyShaderModule(device, shader, nullptr);
        if (device) vkDestroyDevice(device, nullptr);
        if (instance) vkDestroyInstance(instance, nullptr);
    }
    VkPipelineCache cache(const std::vector<std::uint8_t>& previous = {}) {
        VkPipelineCacheCreateInfo info{VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO};
        info.initialDataSize = previous.size();
        info.pInitialData = previous.empty() ? nullptr : previous.data();
        VkPipelineCache out = VK_NULL_HANDLE;
        CHECK_VK(vkCreatePipelineCache(device, &info, nullptr, &out));
        return out;
    }
    double compile(VkPipelineCache cache) {
        VkPipeline pipe = VK_NULL_HANDLE;
        const auto start = Clock::now();
        CHECK_VK(vkCreateComputePipelines(device, cache, 1, &ci, nullptr, &pipe));
        const auto end = Clock::now();
        vkDestroyPipeline(device, pipe, nullptr);
        return std::chrono::duration<double, std::milli>(end - start).count();
    }
};

int main() {
    try {
        Device vk;
        // Cache handles must never be accessed concurrently by two threads.
        auto live = vk.cache();
        auto worker = vk.cache();
        const auto run_live = std::async(std::launch::async, [&] { return vk.compile(live); });
        const auto run_worker = std::async(std::launch::async, [&] { return vk.compile(worker); });
        const double live_cold_ms = run_live.get();
        const double worker_cold_ms = run_worker.get();

        CHECK_VK(vkMergePipelineCaches(vk.device, live, 1, &worker));
        std::size_t count = 0;
        CHECK_VK(vkGetPipelineCacheData(vk.device, live, &count, nullptr));
        if (count < 32 || count > 64 * 1024 * 1024) {
            throw std::runtime_error("Invalid size of merged pipeline cache snapshot");
        }
        std::vector<std::uint8_t> data(count);
        const auto got = vkGetPipelineCacheData(vk.device, live, &count, data.data());
        if (got != VK_SUCCESS) throw std::runtime_error("Pipeline cache snapshot incomplete");
        data.resize(count);
        auto restored = vk.cache(data);

        // Make a new VkPipeline with restored cache; Vulkan allows drivers to
        // ignore cache contents, so we report timings but do not claim speedup.
        const double restored_ms = vk.compile(restored);
        auto untouched = vk.cache();
        const double unrelated_cold_ms = vk.compile(untouched);

        std::printf("GOW3_VK_CACHE_PREFLIGHT host=\"%s\" separate_cache_concurrent=ok "
                    "worker_merge=ok snapshot_restore=ok snapshot_bytes=%zu "
                    "live_cold_ms=%.5f worker_cold_ms=%.5f restored_ms=%.5f "
                    "new_cache_ms=%.5f\n", vk.name, data.size(),
                    live_cold_ms, worker_cold_ms, restored_ms, unrelated_cold_ms);
        std::puts("LIMITATION: Host compute shader cache, NOT Mali/PanVK graphics "
                  "pipeline compile nor game FPS; no performance promotion from this test.");
        vkDestroyPipelineCache(vk.device, untouched, nullptr);
        vkDestroyPipelineCache(vk.device, restored, nullptr);
        vkDestroyPipelineCache(vk.device, worker, nullptr);
        vkDestroyPipelineCache(vk.device, live, nullptr);
        return 0;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "GOW3_VK_CACHE_PREFLIGHT failed: %s\n", e.what());
        return 2;
    }
}
