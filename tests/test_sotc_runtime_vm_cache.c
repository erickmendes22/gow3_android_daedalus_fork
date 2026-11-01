/* Source-level portable regression for the SotC Bionic VM metadata cache.
 * Link only selected code, never create Vulkan/guest CPU objects.
 */
#define _GNU_SOURCE
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
    puts("SotC Bionic VM interval cache: changed/unrelated/overflow/adjacent/hole/concurrent OK");
    free(vmas);free(backing_base);
    return 0;
}