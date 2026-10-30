/* SPDX-License-Identifier: GPL-2.0-or-later
 * SotC's packed 31-bit pointers require the guest image below 2 GiB.
 * MAP_FIXED_NOREPLACE must not be replaced with destructive MAP_FIXED.
 */
#define _GNU_SOURCE
#include "lowmem.h"
#include <stdint.h>
#include <sys/mman.h>
#include <unistd.h>
#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif
#define MIN_ADDR UINT64_C(0x04000000)
#define LIMIT UINT64_C(0x80000000)
#define STEP UINT64_C(0x01000000)
static size_t page_ceil(size_t n, size_t p) {
    if (!n || !p || n > SIZE_MAX - (p-1)) return 0;
    return (n+p-1)/p*p;
}
void *sotc_map_guest_image(size_t bytes) {
    long ps=sysconf(_SC_PAGESIZE);
    if (ps<=0) return NULL;
    size_t size=page_ceil(bytes,(size_t)ps);
    if (!size || (uint64_t)size>=LIMIT-MIN_ADDR) return NULL;
    for(uint64_t at=MIN_ADDR; at+size<=LIMIT; at+=STEP) {
        void *p=mmap((void *)(uintptr_t)at,size,PROT_READ|PROT_WRITE,
                      MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (p==MAP_FAILED) continue;
        if ((uintptr_t)p==(uintptr_t)at) return p;
        munmap(p,size); /* old kernel may have treated at as a hint */
    }
    return NULL; /* Never silently fall back to >=2 GiB. */
}
void sotc_unmap_guest_image(void *image,size_t bytes) {
    long ps=sysconf(_SC_PAGESIZE);
    if (!image || ps<=0) return;
    size_t size=page_ceil(bytes,(size_t)ps);
    if(size) munmap(image,size);
}
