/* Shadow of the Colossus original Vulkan renderer dispatch.
 * Kept separate from the GoW3 Vulkan core and only selected for BBPROBE5.
 */
#pragma once
#include <stdint.h>
#include "gpu/gow3gpu.h"
#ifdef __cplusplus
extern "C" {
#endif
int sotc_gpu_load(int required);
int sotc_gpu_available(void);
void sotc_gpu_register_kernel(void);
int sotc_gpu_init(const Gow3GpuConfig *config);
uintptr_t sotc_gpu_resolve(const char *nid);
int sotc_gpu_handle_fault(void *ucontext, void *address);
void sotc_gpu_dump_guest_writes(void *ucontext);
unsigned sotc_gpu_symbol_count(void);
#ifdef __cplusplus
}
#endif
