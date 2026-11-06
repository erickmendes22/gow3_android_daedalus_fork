/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>
#if defined(__aarch64__) && defined(__ARM_NEON)
#include <arm_neon.h>
#endif

/* Interleave eight-bit planar chroma without a temporary AVFrame. Each source
 * row has chroma_width samples (covering 2*chroma_width luma pixels); the
 * destination has 2*chroma_width bytes. Source and destination do not alias. */
static inline void gow3_interleave_uv_row(uint8_t *dst, const uint8_t *u,
                                          const uint8_t *v, size_t chroma_width) {
    size_t x = 0;
#if defined(__aarch64__) && defined(__ARM_NEON)
    for (; x + 16 <= chroma_width; x += 16) {
        const uint8x16x2_t chroma = {{vld1q_u8(u + x), vld1q_u8(v + x)}};
        vst2q_u8(dst + 2 * x, chroma);
    }
#endif
    for (; x < chroma_width; ++x) {
        dst[2 * x] = u[x];
        dst[2 * x + 1] = v[x];
    }
}
