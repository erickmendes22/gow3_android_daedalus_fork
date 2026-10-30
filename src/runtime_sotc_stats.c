/* SotC GPU diagnostics that are not measured by the GoW3 VM implementation.
 * The actual mapping/readback APIs are implemented in runtime_memory.c.
 * Zero values here mean no Windows placeholder-carve events or no counters
 * are collected on Bionic, not that a real latency measurement was made.
 */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
uint64_t runtime_memory_carve_splits(void) { return 0; }
void runtime_memory_lock_stats(uint64_t *writes,double *wait_ms,double *hold_ms,double *worst_ms) {
    if(writes) *writes=0;
    if(wait_ms) *wait_ms=0;
    if(hold_ms) *hold_ms=0;
    if(worst_ms) *worst_ms=0;
}
void runtime_memory_lock_stats2(double *worst_hold_ms,uint64_t *read_waits,double *read_wait_ms) {
    if(worst_hold_ms) *worst_hold_ms=0;
    if(read_waits) *read_waits=0;
    if(read_wait_ms) *read_wait_ms=0;
}
void runtime_memory_lock_sites(char *readers,char *writers,size_t capacity) {
    if(!capacity) return;
    if(readers) readers[0]=0;
    if(writers) writers[0]=0;
}
void runtime_memory_carve_stats(uint64_t *mib,uint64_t *runs,double *split_ms,double *worst_ms,double *other_ms) {
    if(mib) *mib=0;
    if(runs) *runs=0;
    if(split_ms) *split_ms=0;
    if(worst_ms) *worst_ms=0;
    if(other_ms) *other_ms=0;
}
void runtime_memory_cache_stats(uint64_t *misses,uint64_t *stale,uint64_t *fast) {
    if(misses) *misses=0;
    if(stale) *stale=0;
    if(fast) *fast=0;
}
uint64_t runtime_file_read_ns_take(void) { return 0; }

/* SotC heap guard is unavailable until the game's heap allocation can be
 * captured from FEX guest callbacks. Report zero so GPU never assumes the
 * guarded table has been discovered.
 */
uintptr_t runtime_sotc_heap(void) { return 0; }
uintptr_t runtime_sotc_heap_table(void) { return 0; }
