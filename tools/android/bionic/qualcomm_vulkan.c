// SPDX-License-Identifier: GPL-2.0-or-later
#define _XOPEN_SOURCE 700
#include <dlfcn.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan_core.h>

// libadrenotools at 8fae8ce254dfc1344527e05301e43f37dea2df80.
typedef void *(*OpenAdrenoVulkan)(int, int, const char *, const char *,
                                 const char *, const char *, const char *, void **);
enum { ADRENOTOOLS_DRIVER_CUSTOM = 1 };

static pthread_once_t loader_once = PTHREAD_ONCE_INIT;
static pthread_once_t mapping_once = PTHREAD_ONCE_INIT;
static PFN_vkGetInstanceProcAddr isolated_gipa;
static bool selected_driver_mapped;

static void OpenQualcommDriver(void) {
    const char *driver = getenv("GOW3_QUALCOMM_VULKAN_DRIVER");
    const char *hooks = getenv("GOW3_QUALCOMM_HOOK_DIR");
    const char *basename = driver ? strrchr(driver, '/') : NULL;
    if (!basename || !basename[1] || !hooks || !*hooks) {
        dprintf(2, "Vulkan: imported Qualcomm driver configuration missing\n");
        return;
    }

    char hook_dir[PATH_MAX], driver_dir[PATH_MAX], helper[PATH_MAX];
    const size_t driver_len = (size_t)(basename - driver) + 1;
    const int hook_len = snprintf(hook_dir, sizeof(hook_dir), "%s/", hooks);
    const int helper_len = snprintf(helper, sizeof(helper), "%s/libadrenotools.so", hooks);
    if (driver_len >= sizeof(driver_dir) || hook_len < 0 || helper_len < 0 ||
        (size_t)hook_len >= sizeof(hook_dir) || (size_t)helper_len >= sizeof(helper)) {
        dprintf(2, "Vulkan: imported Qualcomm driver path is too long\n");
        return;
    }
    memcpy(driver_dir, driver, driver_len);
    driver_dir[driver_len] = '\0';

    const int flags = RTLD_NOW | RTLD_LOCAL;
    void *tools = dlopen(helper, flags);
    OpenAdrenoVulkan open = tools ? (OpenAdrenoVulkan)dlsym(tools, "adrenotools_open_libvulkan") : NULL;
    if (!open) {
        const char *error = dlerror();
        dprintf(2, "Vulkan: could not initialize imported Qualcomm loader: %s\n",
                error ? error : "missing libadrenotools entry point");
        return;
    }
    void *loader = open(flags, ADRENOTOOLS_DRIVER_CUSTOM, NULL, hook_dir, driver_dir,
                        basename + 1, NULL, NULL);
    if (!loader) {
        dprintf(2, "Vulkan: imported Qualcomm vendor namespace initialization failed for %s\n", driver);
        return;
    }
    isolated_gipa = (PFN_vkGetInstanceProcAddr)dlsym(loader, "vkGetInstanceProcAddr");
    dprintf(2, "Vulkan: imported Qualcomm isolated loader for %s (%s)\n",
            driver, isolated_gipa ? "ready" : "missing vkGetInstanceProcAddr");
}

static void VerifySelectedDriver(void) {
    const char *driver = getenv("GOW3_QUALCOMM_VULKAN_DRIVER");
    char expected[PATH_MAX];
    FILE *maps = realpath(driver, expected) ? fopen("/proc/self/maps", "r") : NULL;
    if (maps) {
        char line[PATH_MAX + 256];
        while (fgets(line, sizeof(line), maps)) {
            char *path = strchr(line, '/');
            if (path) {
                path[strcspn(path, "\n")] = '\0';
                if (strcmp(path, expected) == 0) {
                    selected_driver_mapped = true;
                    break;
                }
            }
        }
        fclose(maps);
    }
    dprintf(2, "GoW III Qualcomm: %s: %s\n",
            selected_driver_mapped ? "verified selected ICD mapped" : "selected ICD was not mapped",
            driver);
}

static VKAPI_ATTR VkResult VKAPI_CALL EnumeratePhysicalDevices(VkInstance instance,
                                                               uint32_t *count,
                                                               VkPhysicalDevice *devices) {
    PFN_vkEnumeratePhysicalDevices enumerate =
        (PFN_vkEnumeratePhysicalDevices)isolated_gipa(instance, "vkEnumeratePhysicalDevices");
    VkResult result = enumerate(instance, count, devices);
    if ((result == VK_SUCCESS || result == VK_INCOMPLETE) && *count > 0) {
        pthread_once(&mapping_once, VerifySelectedDriver);
        if (!selected_driver_mapped) {
            *count = 0;
            return VK_ERROR_INCOMPATIBLE_DRIVER;
        }
    }
    return result;
}

VKAPI_ATTR __attribute__((visibility("default"))) PFN_vkVoidFunction VKAPI_CALL
vkGetInstanceProcAddr(VkInstance instance, const char *name) {
    pthread_once(&loader_once, OpenQualcommDriver);
    PFN_vkVoidFunction proc = isolated_gipa ? isolated_gipa(instance, name) : NULL;
    if (proc && strcmp(name, "vkEnumeratePhysicalDevices") == 0) {
        return (PFN_vkVoidFunction)EnumeratePhysicalDevices;
    }
    return proc;
}
