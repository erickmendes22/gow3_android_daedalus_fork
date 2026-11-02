/* SotC GPU backing-write synthetic A/B: same validated VMA layout and bytes.
 * This measures only the memory runtime, NOT FPS on a Redmagic/Adreno.
 */
#define _GNU_SOURCE
#include "../src/runtime_memory.c"
#include <assert.h>
#include <stdio.h>
static __thread int32_t fake_errno;
int32_t *runtime_errno(void) { return &fake_errno; }

int main(void) {
    enum { LOOPS_SMALL=300000, LOOPS_LARGE=18000 };
    const uintptr_t first=USER_MIN+0x600000;
    backing_base=(unsigned char *)calloc(1,4*PAGE);
    vma_capacity=2;
    vmas=(Vma *)calloc(vma_capacity,sizeof(*vmas));
    assert(backing_base && vmas);
    vmas[0]=(Vma){first,first+2*PAGE,KIND_DIRECT,0x33,0,0};
    vmas[1]=(Vma){first+2*PAGE,first+4*PAGE,KIND_DIRECT,0x33,0,2*PAGE};
    vma_count=2;
    uintptr_t lo=0,hi=0;int mapped=0;
    assert(runtime_memory_region(first+PAGE,&lo,&hi,&mapped)&&mapped);
    assert(runtime_memory_region(first+2*PAGE,&lo,&hi,&mapped)&&mapped);
    unsigned char *data=(unsigned char *)malloc(64*1024);
    assert(data);
    for (unsigned i=0;i<64*1024;++i)data[i]=(unsigned char)(i*11);
    const char *v=getenv("SOTC_WRITE_FAST");
    for (unsigned kind=0;kind<2;++kind) {
        const unsigned n=kind?LOOPS_LARGE:LOOPS_SMALL;
        const unsigned size=kind?65536u:512u;
        const uintptr_t guest=kind?first:first+PAGE;
        struct timespec start,finish;
        clock_gettime(CLOCK_MONOTONIC,&start);
        for(unsigned i=0;i<n;++i)
            assert(runtime_memory_write_backing(guest,data,size)==1);
        clock_gettime(CLOCK_MONOTONIC,&finish);
        double ms=(finish.tv_sec-start.tv_sec)*1000.0+
                  (finish.tv_nsec-start.tv_nsec)/1000000.0;
        assert(backing_base[0]==data[0]);
        printf("SotC writeback synthetic: fast=%s bytes=%u iterations=%u ms=%.3f calls/s=%.0f\n",
               v?v:"1",size,n,ms,n*1000.0/ms);
    }
    free(data);free(vmas);free(backing_base);
    return 0;
}
