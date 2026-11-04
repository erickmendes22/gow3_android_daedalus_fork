// SPDX-License-Identifier: GPL-3.0-only
// Adapted from The412Banner/Bannerlator 0ab047311ccc55b2911d984727d2d57ac6c0ebf7.
// Ported from DroidDeck PRs #1969 and #1981.
#ifndef BANNERLATOR_KGSL_BUSY_H
#define BANNERLATOR_KGSL_BUSY_H
#include <stddef.h>
#include <stdint.h>
#define KGSL_BUSY_ENTRY_WORDS 10
#define KGSL_BUSY_SOP 0
#define KGSL_BUSY_EOP 2
#define KGSL_BUSY_SLOTS 5
static inline int kgsl_busy_first_slot(size_t bytes) {
    size_t entries = bytes / (KGSL_BUSY_ENTRY_WORDS * sizeof(uint32_t));
    return entries < 8 ? -1 : (int)(entries - 6);
}
static inline int kgsl_busy_sample(const volatile uint32_t *memstore, int first,
                                   uint32_t last[KGSL_BUSY_SLOTS], int *moved) {
    int busy = 0;
    for (int i = 0; i < KGSL_BUSY_SLOTS; i++) {
        const volatile uint32_t *entry = memstore + (size_t)(first + i) * KGSL_BUSY_ENTRY_WORDS;
        uint32_t sop = entry[KGSL_BUSY_SOP], eop = entry[KGSL_BUSY_EOP];
        if (sop != eop) busy = 1;
        if (sop != last[i]) { *moved = 1; last[i] = sop; }
    }
    return busy;
}
#define KGSL_BUSY_MAX_LIVE 64
static inline int kgsl_busy_scan_contexts(const volatile uint32_t *memstore, int first,
                                           uint32_t *seen, int *live, int max_live) {
    int n = 0, idle = 0;
    int idle_ids[KGSL_BUSY_MAX_LIVE];
    for (int id = 1; id < first; id++) {
        const volatile uint32_t *entry = memstore + (size_t)id * KGSL_BUSY_ENTRY_WORDS;
        uint32_t sop = entry[KGSL_BUSY_SOP], eop = entry[KGSL_BUSY_EOP];
        int changed = sop != seen[id];
        seen[id] = sop;
        if ((changed || sop != eop) && n < max_live) live[n++] = id;
        else if (sop != 0 && idle < KGSL_BUSY_MAX_LIVE) idle_ids[idle++] = id;
    }
    for (int i = 0; i < idle && n < max_live; i++) live[n++] = idle_ids[i];
    return n;
}
static inline int kgsl_busy_sample_contexts(const volatile uint32_t *memstore,
                                            const int *live, int count, uint32_t *last, int *moved) {
    int busy = 0;
    for (int i = 0; i < count; i++) {
        const volatile uint32_t *entry = memstore + (size_t)live[i] * KGSL_BUSY_ENTRY_WORDS;
        uint32_t sop = entry[KGSL_BUSY_SOP], eop = entry[KGSL_BUSY_EOP];
        if (sop != eop) busy = 1;
        if (sop != last[live[i]]) { *moved = 1; last[live[i]] = sop; }
    }
    return busy;
}
#endif
