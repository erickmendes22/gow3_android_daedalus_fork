/* Reproducible non-device comparison of SotC GPU VMA query overhead.
 * The guest streams mappings while a GPU thread queries >8 distinct regions.
 * Benchmarks are NOT FPS or Android performance predictions.
 */
#define _GNU_SOURCE
#include "../src/runtime_memory.c"
#include <assert.h>
#include <stdio.h>
static __thread int32_t mock_errno;
int32_t *runtime_errno(void) { return &mock_errno; }
int main(void) {
    enum { REGIONS=32, LOOKUPS=1000000 };
    const uintptr_t first=USER_MIN+0x400000;
    const uintptr_t unrelated=USER_MIN+0x40000000;
    vma_capacity=REGIONS;
    vma_count=REGIONS;
    vmas=(Vma *)calloc(vma_capacity,sizeof(*vmas));
    assert(vmas);
    for (unsigned i=0;i<REGIONS;i++) {
        const uintptr_t a=first+i*(PAGE*2);
        vmas[i]=(Vma){a,a+PAGE,KIND_DIRECT,0x33,0,i*PAGE};
    }
    struct timespec ts0,ts1;
    volatile unsigned checksum=0;
    assert(clock_gettime(CLOCK_MONOTONIC,&ts0)==0);
    for (unsigned i=0;i<LOOKUPS;++i) {
        if ((i&127u)==0) {
            write_lock();
            sotc_vm_mark_dirty(unrelated,unrelated+PAGE);
            write_unlock();
        }
        const uintptr_t a=first+(i%REGIONS)*(PAGE*2);
        uintptr_t start=0,end=0;
        int mapped=0;
        assert(runtime_memory_region(a,&start,&end,&mapped)==1);
        assert(mapped && start==a && end==a+PAGE);
        checksum += (unsigned)(start/PAGE);
    }
    assert(clock_gettime(CLOCK_MONOTONIC,&ts1)==0);
    const double ms=(ts1.tv_sec-ts0.tv_sec)*1000.0+
        (ts1.tv_nsec-ts0.tv_nsec)/1000000.0;
    printf("SotC VMA synthetic guest-query benchmark: cache=%s, %u lookups, %.3f ms, %.0f queries/s, checksum=%u\n",
        getenv("SOTC_VM_RANGE_CACHE") ? getenv("SOTC_VM_RANGE_CACHE") : "1",
        LOOKUPS,ms,LOOKUPS*1000.0/ms,(unsigned)checksum);
    free(vmas);
    return 0;
}
