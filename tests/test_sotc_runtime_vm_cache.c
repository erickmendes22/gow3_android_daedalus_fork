/* Source-level portable regression for the SotC Bionic VM metadata cache.
 * Link only selected code, never create Vulkan/guest CPU objects.
 */
#define _GNU_SOURCE
#define SOTC_VM_FAST_TEST 1
#include "../src/runtime_memory.c"
#include <assert.h>
#include <stdio.h>
/* The extracted single-translation-unit host test does not link probe.c. */
static __thread int32_t test_errno;
int32_t *runtime_errno(void) { return &test_errno; }
/* Real independent thread writes many unrelated mapping generations.
 * The reader may use a verified cached mapping or fall back to the lock.
 */
static void *unrelated_writer(void *arg) {
    const uintptr_t other=*(const uintptr_t *)arg;
    for (int i=0;i<4000;++i) {
        write_lock();
        sotc_vm_mark_dirty(other,other+PAGE);
        write_unlock();
    }
    return NULL;
}
static int sotc_test_wb_stage;
static void *sotc_test_remapper(void *ctx) {
    const uintptr_t address=*(const uintptr_t *)ctx;
    __atomic_store_n(&sotc_test_wb_stage,1,__ATOMIC_RELEASE);
    write_lock(); // must wait for the held fast-copy ticket
    sotc_vm_mark_dirty(address,address+PAGE);
    __atomic_store_n(&sotc_test_wb_stage,2,__ATOMIC_RELEASE);
    write_unlock();
    return NULL;
}
int main(void) {
    /* An initially mapped region; the backing view is a fixed physical pool. */
    backing_base=(unsigned char *)calloc(1,2*PAGE);
    assert(backing_base);
    vma_capacity=3;
    vmas=(Vma *)calloc(vma_capacity,sizeof(*vmas));
    assert(vmas);
    const uintptr_t first=USER_MIN+0x20000;
    const uintptr_t other=USER_MIN+0x80000;
    write_lock();
    vmas[0]=(Vma){first,first+4096,KIND_DIRECT,0x33,0,0};
    vma_count=1;
    sotc_vm_mark_dirty(first,first+4096);
    write_unlock();
    assert(runtime_memory_is_mapped(first,4096));
    assert(runtime_memory_backing_pointer(first+11)==backing_base+11);
    assert(cached_region(first)!=NULL);
    uint64_t initial=__atomic_load_n(&table_generation,__ATOMIC_ACQUIRE);
    for (int i=0;i<35;i++) {
        write_lock();
        sotc_vm_mark_dirty(other,other+PAGE);
        write_unlock();
    }
    assert(__atomic_load_n(&table_generation,__ATOMIC_RELAXED)==initial+70);
    assert(cached_region(first)!=NULL); /* unrelated writes keep mapping */
    assert(runtime_memory_backing_pointer(first+20)==backing_base+20);
    /* When the mapping itself changes, the old cached metadata MUST miss. */
    write_lock();
    sotc_vm_mark_dirty(first,first+4096);
    vmas[0].kind=KIND_RESERVED;
    write_unlock();
    assert(cached_region(first)==NULL);
    assert(!runtime_memory_is_mapped(first,4096));
    assert(runtime_memory_backing_pointer(first)==NULL);
    /* A journal overflow fails closed, instead of accepting old metadata. */
    write_lock();
    vmas[0].kind=KIND_DIRECT;
    sotc_vm_mark_dirty(first,first+4096);
    write_unlock();
    assert(runtime_memory_is_mapped(first,4096));
    for(int i=0;i<80;i++) {
        write_lock();
        sotc_vm_mark_dirty(other,other+PAGE);
        write_unlock();
    }
    assert(cached_region(first)==NULL);
    assert(runtime_memory_is_mapped(first,4096));
    /* Two adjacent 16-KiB guest mappings are contiguous in GPU address space. */
    write_lock();
    sotc_vm_mark_dirty(first,first+2*PAGE);
    vmas[0].end=first+PAGE;
    vmas[1]=(Vma){first+PAGE,first+2*PAGE,KIND_DIRECT,0x33,0,PAGE};
    vma_count=2;
    write_unlock();
    assert(runtime_memory_clamp(first,2*PAGE)==2*PAGE); /* slow lookup primes both */
    assert(runtime_memory_clamp(first,2*PAGE)==2*PAGE); /* verified cache path */
    assert(runtime_memory_is_mapped(first,2*PAGE));
    assert(sotc_vm_direct[sotc_vm_slot(first+PAGE)].end==first+2*PAGE);
    /* A hole must immediately invalidate the second piece and never return full coverage. */
    write_lock();
    sotc_vm_mark_dirty(first+PAGE,first+2*PAGE);
    vmas[1].kind=KIND_RESERVED;
    write_unlock();
    assert(runtime_memory_clamp(first,2*PAGE)==PAGE);
    assert(!runtime_memory_is_mapped(first,2*PAGE));
    pthread_t worker;
    assert(pthread_create(&worker,NULL,unrelated_writer,(void *)&other)==0);
    for (int i=0;i<10000;++i) {
        uintptr_t lo=0,hi=0;
        int mapped=0;
        assert(runtime_memory_region(first,&lo,&hi,&mapped));
        assert(mapped && lo==first && hi==first+PAGE);
        assert(runtime_memory_backing_pointer(first+11)==backing_base+11);
    }
    assert(pthread_join(worker,NULL)==0);
    /* Rebind both 16 KiB guest VMAs as independently backed, then prime
     * the cache. A 512-byte GPU readback crosses the VMA boundary. */
    write_lock();
    sotc_vm_mark_dirty(first,first+2*PAGE);
    vmas[0].kind=KIND_DIRECT;
    vmas[0].phys=0;
    vmas[1].kind=KIND_DIRECT;
    vmas[1].phys=PAGE;
    write_unlock();
    uintptr_t lo=0,hi=0; int mapped=0;
    assert(runtime_memory_region(first,&lo,&hi,&mapped) && mapped);
    assert(runtime_memory_region(first+PAGE,&lo,&hi,&mapped) && mapped);
    unsigned char payload[512];
    for (unsigned i=0;i<512;++i) payload[i]=(unsigned char)(i*37+17);
    uint64_t fast_before=sotc_write_fast_hits;
    assert(runtime_memory_write_backing(first+PAGE-256,payload,sizeof(payload))==1);
    assert(sotc_write_fast_hits==fast_before+1); // real fast path, two VMAs
    assert(memcmp(backing_base+PAGE-256,payload,256)==0);
    assert(memcmp(backing_base+PAGE,payload+256,256)==0);

    /* Remap invalidates the cache; the old physical page is not modified. */
    write_lock();
    sotc_vm_mark_dirty(first+PAGE,first+2*PAGE);
    vmas[1].phys=0;
    write_unlock();
    const unsigned char replacement[]={0xde,0xad,0xbe,0xef};
    fast_before=sotc_write_fast_hits;
    assert(runtime_memory_write_backing(first+PAGE+32,replacement,sizeof(replacement))==1);
    assert(sotc_write_fast_hits==fast_before); // read-locked fallback
    assert(memcmp(backing_base+32,replacement,sizeof(replacement))==0);
    // The fallback must seed the thread-local mapping cache. A second
    // identical guest-GPU write then takes the fast path with the NEW phys.
    assert(runtime_memory_write_backing(first+PAGE+32,replacement,sizeof(replacement))==1);
    assert(sotc_write_fast_hits==fast_before+1);
    assert(memcmp(backing_base+32,replacement,sizeof(replacement))==0);

    /* Reserved page must return failure; original fallback may write the
     * earlier mapped part, matching its previous partial-write semantics. */
    write_lock();
    sotc_vm_mark_dirty(first+PAGE,first+2*PAGE);
    vmas[1].kind=KIND_RESERVED;
    write_unlock();
    assert(runtime_memory_write_backing(first+PAGE-2,payload,8)==0);

    /* A remapping thread MUST wait for the atomic copy ticket. */
    assert(sotc_wb_copy_enter());
    __atomic_store_n(&sotc_test_wb_stage,0,__ATOMIC_RELEASE);
    pthread_t remapper;
    assert(pthread_create(&remapper,NULL,sotc_test_remapper,(void *)&first)==0);
    for (int spin=0;spin<1000000 &&
         !(__atomic_load_n(&sotc_wb_gate,__ATOMIC_ACQUIRE)&SOTC_WB_GATE_WRITER);++spin)
        sched_yield();
    assert(__atomic_load_n(&sotc_wb_gate,__ATOMIC_ACQUIRE)&SOTC_WB_GATE_WRITER);
    assert(__atomic_load_n(&sotc_test_wb_stage,__ATOMIC_ACQUIRE)==1);
    assert(!sotc_wb_copy_enter()); // gate closed; original fallback waits on lock
    sotc_wb_copy_leave();
    assert(pthread_join(remapper,NULL)==0);
    assert(__atomic_load_n(&sotc_test_wb_stage,__ATOMIC_ACQUIRE)==2);
    assert(__atomic_load_n(&sotc_wb_gate,__ATOMIC_ACQUIRE)==0);
    assert(runtime_memory_write_backing(first,payload,0)==1);
    puts("SotC GPU backing fast write: two VMAs / remap / hole / concurrent writer OK");
    puts("SotC Bionic VM interval cache: changed/unrelated/overflow/adjacent/hole/concurrent OK");
    free(vmas);free(backing_base);
    return 0;
}