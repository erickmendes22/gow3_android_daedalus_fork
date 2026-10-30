/* SPDX-License-Identifier: GPL-2.0-or-later
 * SotC renderer bridge: original bbgpu exports, never GoW3 GPU substitutions.
 * The two GPU cores cannot share renderer singleton state in one process.
 */
#define _GNU_SOURCE
#include "gpu_bridge.h"
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    void *handle;
    void (*register_kernel)(void);
    int (*init)(const Gow3GpuConfig *);
    uintptr_t (*resolve)(const char *);
    int (*handle_fault)(void *, void *);
    void (*dump_writes)(void *);
    unsigned (*symbol_count)(void);
} SotcGpuApi;

static SotcGpuApi gpu;

int sotc_gpu_available(void) { return gpu.handle != NULL; }

int sotc_gpu_load(int required) {
    if (gpu.handle) return 0;
    const char *path=getenv("SOTC_GPU_LIBRARY");
    if (!path || !*path) path="libbbgpu.so";
    void *handle=dlopen(path,RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
        fprintf(stderr,"SotC Vulkan: cannot load original %s: %s\n",path,dlerror());
        return required ? -1 : 0;
    }
    SotcGpuApi api={0};
    api.handle=handle;
    api.register_kernel=(void (*)(void))dlsym(handle,"bbgpu_register_kernel");
    api.init=(int (*)(const Gow3GpuConfig *))dlsym(handle,"bbgpu_init");
    api.resolve=(uintptr_t (*)(const char *))dlsym(handle,"bbgpu_resolve");
    api.handle_fault=(int (*)(void *,void *))dlsym(handle,"bbgpu_handle_fault");
    api.dump_writes=(void (*)(void *))dlsym(handle,"bbgpu_dump_guest_writes");
    api.symbol_count=(unsigned (*)(void))dlsym(handle,"bbgpu_symbol_count");
    if (!api.register_kernel || !api.init || !api.resolve || !api.handle_fault || !api.symbol_count) {
        fprintf(stderr,"SotC Vulkan: incompatible bbgpu exports in %s\n",path);
        dlclose(handle);
        return -1;
    }
    gpu=api;
    fprintf(stderr,"SotC Vulkan: loaded original bbgpu exports from %s\n",path);
    return 0;
}

void sotc_gpu_register_kernel(void) { if (gpu.register_kernel) gpu.register_kernel(); }
int sotc_gpu_init(const Gow3GpuConfig *config) { return gpu.init ? gpu.init(config) : -1; }
uintptr_t sotc_gpu_resolve(const char *nid) { return gpu.resolve ? gpu.resolve(nid) : 0; }
int sotc_gpu_handle_fault(void *ucontext,void *address) {
    return gpu.handle_fault ? gpu.handle_fault(ucontext,address) : 0;
}
void sotc_gpu_dump_guest_writes(void *ucontext) {
    if (gpu.dump_writes) gpu.dump_writes(ucontext);
}
unsigned sotc_gpu_symbol_count(void) { return gpu.symbol_count ? gpu.symbol_count() : 0; }
