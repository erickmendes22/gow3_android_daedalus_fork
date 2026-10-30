/* Native contract test for SotC memory queries and fragmentation. */
#define _GNU_SOURCE
#include "../src/runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int32_t guest_errno;
int32_t *runtime_errno(void) { return &guest_errno; }
uintptr_t runtime_lookup(const RuntimeExport *table, size_t count, const char *name) {
    for (size_t i=0;i<count;++i)
        if (!strcmp(table[i].name,name)) return (uintptr_t)table[i].function;
    return 0;
}
typedef int32_t (ABI *DirectAvailable)(int64_t,int64_t,uint64_t,int64_t*,uint64_t*);
typedef int32_t (ABI *FlexibleAvailable)(uint64_t*);
typedef uint64_t (ABI *DirectSize)(void);
typedef int32_t (ABI *DirectAlloc)(int64_t,int64_t,uint64_t,uint64_t,int,int64_t*);
typedef int32_t (ABI *DirectFree)(uint64_t,uint64_t);
typedef int32_t (ABI *FlexMap)(void **,uint64_t,int,int);
typedef int32_t (ABI *FlexUnmap)(void *,uint64_t);

int main(void) {
    DirectAvailable available=(DirectAvailable)runtime_memory_resolve("sceKernelAvailableDirectMemorySize");
    FlexibleAvailable flexible=(FlexibleAvailable)runtime_memory_resolve("sceKernelAvailableFlexibleMemorySize");
    DirectSize total=(DirectSize)runtime_memory_resolve("pO96TwzOm5E#libkernel");
    DirectAlloc allocate=(DirectAlloc)runtime_memory_resolve("rTXw65xmLIA#libkernel");
    DirectFree release=(DirectFree)runtime_memory_resolve("MBuItvba6z8#libkernel");
    FlexMap map=(FlexMap)runtime_memory_resolve("sceKernelMapFlexibleMemory");
    FlexUnmap unmap=(FlexUnmap)runtime_memory_resolve("cQke9UuBQOk#libkernel");
    assert(available && flexible && total && allocate && release && map && unmap);
    const uint64_t pool=total(), page=16384, flexible_total=UINT64_C(448)*1024*1024;
    int64_t physical=-1, allocated=-1;
    uint64_t size=0;
    assert(pool>=UINT64_C(5056)*1024*1024);
    assert((uint32_t)available(0,(int64_t)pool,page,NULL,&size)==0x80020016);
    assert((uint32_t)available(0,(int64_t)pool,3,&physical,&size)==0x80020016);
    assert(available(0,(int64_t)pool,0,&physical,&size)==0);
    assert(physical==0 && size==pool);
    assert(allocate(0,(int64_t)pool,0x20000,page,3,&allocated)==0);
    assert(allocated==0);
    assert(available(0,(int64_t)pool,page,&physical,&size)==0);
    assert(physical==0x20000 && size==pool-0x20000);
    assert(available(0,0x40000,page,&physical,&size)==0);
    assert(physical==0x20000 && size==0x20000);
    assert(available(0,0x20000,page,&physical,&size)!=0);
    assert(release(0,0x20000)==0);
    assert(available(0,(int64_t)pool,page,&physical,&size)==0);
    assert(physical==0 && size==pool);

    uint64_t free_bytes=0;
    assert((uint32_t)flexible(NULL)==0x80020016);
    assert(flexible(&free_bytes)==0 && free_bytes==flexible_total);
    void *mapped=NULL;
    assert(map(&mapped,page,0x33,0)==0 && mapped);
    assert(flexible(&free_bytes)==0 && free_bytes==flexible_total-page);
    assert(unmap(mapped,page)==0);
    assert(flexible(&free_bytes)==0 && free_bytes==flexible_total);
    puts("SotC direct and flexible memory availability ABI: PASS");
    return 0;
}
