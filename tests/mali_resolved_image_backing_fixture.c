// Exercise the exact implementation extracted from runtime_memory.c.
#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/mman.h>
#include <pthread.h>
#include <fcntl.h>
enum { KIND_RESERVED=1, KIND_DIRECT, KIND_FLEXIBLE };
typedef struct { uintptr_t start, end; int kind, prot, type; uint64_t phys; } Vma;
static Vma entries[3], *vmas=entries;
static size_t vma_count=3;
static unsigned char *backing_base;
static pthread_rwlock_t lock=PTHREAD_RWLOCK_INITIALIZER;
static void read_lock(void){assert(!pthread_rwlock_rdlock(&lock));}
static void read_unlock(void){assert(!pthread_rwlock_unlock(&lock));}
static size_t vma_index(uintptr_t address){size_t i=0; while(i<vma_count && vmas[i].end<=address) ++i; return i;}
/* REAL_IMPLEMENTATION */
int main(void) {
    const size_t p=4096;
    int fd=memfd_create("test",0); assert(fd>=0); assert(!ftruncate(fd,2*p));
    backing_base=mmap(NULL,2*p,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0); assert(backing_base!=MAP_FAILED);
    unsigned char *guest=mmap(NULL,5*p,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0); assert(guest!=MAP_FAILED);
    assert(mmap(guest,p,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,fd,0)==guest);
    assert(mmap(guest+3*p,p,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,fd,p)==guest+3*p);
    memset(guest,0x3a,p); memset(guest+3*p,0x71,p);
    assert(!mprotect(guest,p,PROT_NONE)); assert(!mprotect(guest+3*p,p,PROT_NONE));
    entries[0]=(Vma){.start=(uintptr_t)guest,.end=(uintptr_t)guest+p,.kind=KIND_DIRECT,.phys=0};
    entries[1]=(Vma){.start=(uintptr_t)guest+2*p,.end=(uintptr_t)guest+3*p,.kind=KIND_RESERVED};
    entries[2]=(Vma){.start=(uintptr_t)guest+3*p,.end=(uintptr_t)guest+4*p,.kind=KIND_FLEXIBLE,.phys=p};
    unsigned char out[5*4096]; memset(out,0xff,sizeof(out));
    runtime_memory_read_backing_sparse((uintptr_t)guest,out,sizeof(out));
    for(size_t i=0;i<sizeof(out);i++) assert(out[i]==(i<p?0x3a:i>=3*p&&i<4*p?0x71:0));
    backing_base[32]=0xb7;
    runtime_memory_read_backing_sparse((uintptr_t)guest+32,out,1); assert(out[0]==0xb7);
    runtime_memory_read_backing_sparse((uintptr_t)guest+p-2,out,4); assert(out[0]==0x3a&&out[1]==0x3a&&out[2]==0&&out[3]==0);
    puts("PASS: protected pages, shared backing, sparse gaps, reserved ranges, final unmapped range and partial reads");
    return 0;
}
