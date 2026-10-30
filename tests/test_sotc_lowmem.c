#include "../ports/sotc/android/lowmem.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
int main(void) {
    assert(sotc_map_guest_image(0)==NULL);
    assert(sotc_map_guest_image((size_t)0x80000000)==NULL);
    const size_t size=16*1024*1024;
    unsigned char *a=sotc_map_guest_image(size);
    if(!a) { fputs("SKIP: host low VA unavailable\n",stderr); return 77; }
    assert((uintptr_t)a+size<=0x80000000);
    a[0]=0x55; a[size-1]=0xaa;
    assert(a[0]==0x55 && a[size-1]==0xaa);
    unsigned char *b=sotc_map_guest_image(size);
    assert(b && b!=a && (uintptr_t)b+size<=0x80000000);
    sotc_unmap_guest_image(a,size);
    sotc_unmap_guest_image(b,size);
    puts("SotC low VA PASS");
    return 0;
}
