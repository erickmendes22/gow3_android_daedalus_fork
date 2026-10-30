/* SPDX-License-Identifier: GPL-2.0-or-later
 * Exercise the exact NID that stopped the SotC EU 1.01 libc.prx bootstrap.
 * This runs on the host without a GPU, FEX, Android or an eboot dump. */
#define _POSIX_C_SOURCE 200809L
#include "../src/runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int32_t (ABI *AttrInit)(void **);
typedef int32_t (ABI *AttrDestroy)(void **);
typedef int32_t (ABI *AttrType)(void **,int);
int main(void) {
    char scratch[64];
    assert(setenv("SOTC_PORT","1",1)==0);
    assert(!strcmp(runtime_symbol("F8bUHwAG284#0#F"),
                   "scePthreadMutexattrInit"));
    const char *key=runtime_sotc_legacy_import("F8bUHwAG284#0#F",scratch);
    assert(key && !strcmp(key,"F8bUHwAG284#libkernel"));
    AttrInit init=(AttrInit)runtime_mutex_resolve(key);
    AttrType type=(AttrType)runtime_mutex_resolve(
        runtime_sotc_legacy_import("iMp8QpE+XO4#0#F",scratch));
    AttrDestroy destroy=(AttrDestroy)runtime_mutex_resolve(
        runtime_sotc_legacy_import("smWEktiyyG0#0#F",scratch));
    assert(init && type && destroy);
    void *attr=NULL;
    assert((uint32_t)init(NULL)==UINT32_C(0x80020016));
    assert(init(&attr)==0 && attr);
    assert(type(&attr,2)==0);
    assert(destroy(&attr)==0 && attr==NULL);
    /* Explicit non-libkernel library routing and unknown legacy exports. */
    assert(!strcmp(runtime_sotc_legacy_import("R9lA82OraNs#14#F",scratch),
                   "R9lA82OraNs#libSceAppContent"));
    assert(!strcmp(runtime_sotc_legacy_import("JaRMy+QcpeU#0#F",scratch),
                   "JaRMy+QcpeU#libkernel"));
    assert(runtime_sotc_legacy_import("bad#0#F",scratch)==NULL);
    assert(unsetenv("SOTC_PORT")==0);
    assert(runtime_symbol("F8bUHwAG284#0#F")==NULL);
    assert(!strcmp(runtime_symbol("F8bUHwAG284#libkernel"),
                   "scePthreadMutexattrInit"));
    puts("SotC scoped HLE import and pthread mutexattr: PASS");
    return 0;
}
