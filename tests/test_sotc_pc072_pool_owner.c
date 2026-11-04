/* PC v0.71 T38 page-pool ownership backport: actual Bionic VM, no mocks
 * for the VMA logic. Link with garbage collection to avoid GPU dependencies.
 */
#define _GNU_SOURCE
#include "../src/runtime_memory.c"
#include <assert.h>
#include <stdio.h>

static uintptr_t test_guest_rip;
uintptr_t guest_cpu_return_address(uintptr_t native) { (void)native; return test_guest_rip; }
static __thread int32_t err_test;
int32_t *runtime_errno(void) { return &err_test; }

int main(void) {
    assert(setenv("SOTC_POOL_OWNER","1",1)==0);
    const uintptr_t a=USER_MIN+0x400000, b=USER_MIN+0x800000;
    const uintptr_t release=USER_MIN+0x1ac82;
    vmas=calloc(5,sizeof(*vmas)); assert(vmas); vma_capacity=5;
    vmas[0]=(Vma){a,a+3*0x10000,KIND_DIRECT,0x33,0,0};
    vmas[1]=(Vma){b,b+0x10000,KIND_DIRECT,0x33,0,0x10000};
    vma_count=2;
    runtime_memory_set_release_site(release);
    write_lock();
    sotc_owner_note(0,a,3*0x10000);
    sotc_owner_note(0x10000,b,0x10000);
    write_unlock();
    VirtualQueryInfo v;
    test_guest_rip=0;
    assert(virtual_query((void *)(a+0x10000),0,&v,sizeof(v))==0);
    assert(v.flags&16u); /* normal code must see original committed memory */
    test_guest_rip=release;
    assert(virtual_query((void *)(a+0x10000),0,&v,sizeof(v))==0);
    assert(!(v.flags&16u)); /* released block must skip page now owned at b */
    assert(v.start==a+0x10000 && v.end==a+2*0x10000);
    assert(v.offset==0x10000);
    assert(sotc_owner_skipped_pages==1 && sotc_owner_skips==1);
    assert(virtual_query((void *)(a+2*0x10000),0,&v,sizeof(v))==0);
    assert(v.flags&16u); /* next page still has a as its owner */
    assert(virtual_query((void *)b,0,&v,sizeof(v))==0);
    assert(v.flags&16u);
    /* Replacing original page's physical owner is the core of PC's T38 fix. */
    write_lock();
    sotc_owner_note(0x10000,a+0x10000,0x10000);
    write_unlock();
    assert(virtual_query((void *)(a+0x10000),0,&v,sizeof(v))==0);
    assert(v.flags&16u);
    /* v0.71 flexible split must advance the backing, not alias the left side */
    write_lock();
    vmas[0]=(Vma){a,a+3*PAGE,KIND_FLEXIBLE,0x33,0,POOL_SIZE};
    vma_count=1;
    assert(split_at(a+PAGE)==0);
    assert(vmas[1].start==a+PAGE && vmas[1].phys==POOL_SIZE+PAGE);
    write_unlock();
    puts("PASS: SotC PC 0.71 direct-page ownership, no double free, correct flexible split");
    free(sotc_pool_owner);free(vmas);
}
