/* Source-level portable regression for the SotC Bionic VM metadata cache.
 * Link only selected code, never create Vulkan/guest CPU objects.
 */
#define _GNU_SOURCE
#include "../src/runtime_memory.c"
#include <assert.h>
#include <stdio.h>
int main(void) {
    /* An initially mapped region; the backing view is a fixed physical pool. */
    backing_base=(unsigned char *)calloc(1,4096);
    assert(backing_base);
    vma_capacity=2;
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
    puts("SotC Bionic VM interval cache: changed/unrelated/overflow/ABI OK");
    free(vmas);free(backing_base);
    return 0;
}