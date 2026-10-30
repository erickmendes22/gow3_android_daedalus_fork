/* SPDX-License-Identifier: GPL-2.0-or-later
 * Resolve actual SotC symbol NIDs using the GoW3 runtime with SotC mapping.
 * Build with gc-sections: no real GPU or game dump is needed.
 */
#define _POSIX_C_SOURCE 200809L
#include "../src/runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int fake_fiber(void) { return 123; }
static int fake_sdk(void) { return 456; }
int main(void) {
    assert(setenv("SOTC_PORT","1",1)==0);
    assert(!strcmp(runtime_symbol("hVYD7Ou2pCQ#libSceFiber"),
                   "_sceFiberInitializeImpl"));
    assert(!strcmp(runtime_symbol("WB66evu8bsU#libkernel"),
                   "sceKernelGetCompiledSdkVersion"));
    RuntimeExport exports[]={
        {"_sceFiberInitializeImpl",(void *)fake_fiber},
        {"sceKernelGetCompiledSdkVersion",(void *)fake_sdk}
    };
    assert(runtime_lookup(exports,2,"hVYD7Ou2pCQ#libSceFiber")==(uintptr_t)fake_fiber);
    assert(runtime_lookup(exports,2,"WB66evu8bsU#libkernel")==(uintptr_t)fake_sdk);
    assert(runtime_lookup(exports,2,"not-a-NID#libSceFiber")==0);
    assert(unsetenv("SOTC_PORT")==0);
    assert(!strcmp(runtime_symbol("bzQExy189ZI#libc"),"_init_env"));
    assert(runtime_symbol("hVYD7Ou2pCQ#libSceFiber")==NULL);
    puts("SotC NID lookup and GoW3 isolation: PASS");
    return 0;
}
