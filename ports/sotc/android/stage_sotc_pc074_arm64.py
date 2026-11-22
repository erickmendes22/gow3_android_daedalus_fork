#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Port PC v0.74 exact depth/G-buffer register-delta fastpath to Android ARM64.

The PC code compares register dwords using x86 SSE; this changes ONLY that
producer comparison to equivalent scalar AArch64 semantics, preserving the
unchanged fastpath's exact 64-bit dword mask, ordered register deltas, full
draws, image/cache generations, HTile/CMASK, barriers and render state.
No approximate render-target cache or guest draw skip is introduced.
"""
from pathlib import Path


def once(text: str, src: str, dst: str, what: str) -> str:
    count=text.count(src)
    if count != 1:
        raise ValueError(f"SotC PC depth/GBuffer ARM64 source drift: {what} ({count})")
    return text.replace(src,dst,1)


def patch(gpu: Path) -> None:
    gpu=Path(gpu)
    root=gpu/'shadps4/video_core'
    rasterizer=(root/'renderer_vulkan/vk_rasterizer.cpp').read_text()
    liverpool=root/'amdgpu/liverpool.cpp'
    code=liverpool.read_text()
    # These are the exact, upstream-verified PC fast paths. Never substitute
    # the older Android RT memo for them.
    for marker in ('DepthFastBeginCheck', 'GBufferFastCheck', 'BeginRenderingFast',
                   'DepthFastBeginApply', 'GBufferFastApply', 'TransitIsNoop',
                   'ImageSetGeneration', 'MetaEpoch'):
        if marker not in rasterizer:
            raise ValueError('PC #308 required renderer invariant absent: '+marker)
    if 'DrawRelSerial' not in code or 'back_shadow' not in code:
        raise ValueError('PC #308 exact changed-register protocol missing')

    sse='''            for (u32 i = 0; i < RegChunkDwords; i += 4) {
                const __m128i a = _mm_loadu_si128(reinterpret_cast<const __m128i*>(src + i));
                const __m128i b = _mm_loadu_si128(reinterpret_cast<const __m128i*>(shadow + i));
                const u32 equal =
                    static_cast<u32>(_mm_movemask_ps(_mm_castsi128_ps(_mm_cmpeq_epi32(a, b))));
                mask |= u64{(~equal) & 0xFu} << i;
            }'''
    scalar='''#if defined(__aarch64__)
            // Exact bitwise equality, NOT a bytewise approximation. Each set
            // bit carries precisely one differing 32-bit register to the
            // draw thread. Do not alter the mask serialization protocol.
            for (u32 i = 0; i < RegChunkDwords; ++i) {
                if (src[i] != shadow[i])
                    mask |= u64{1} << i;
            }
#else
'''+sse+'''
#endif'''
    code=once(code,sse,scalar,'x86 SIMD PM4 delta compare')
    code=once(code,'''static inline void CpuRelax() {
#if defined(__x86_64__) || defined(_M_X64)
    __builtin_ia32_pause();
#endif
}''','''static inline void CpuRelax() {
#if defined(__x86_64__) || defined(_M_X64)
    __builtin_ia32_pause();
#elif defined(__aarch64__)
    // ARM64 bounded CPU/draw worker wait instead of a busy no-op.
    __asm__ __volatile__("yield" ::: "memory");
#endif
}''','ARM64 wait hint')
    for marker in ('op.reg_chunks.push_back(static_cast<u32>(mask))',
                   'op.reg_chunks.push_back(static_cast<u32>(mask >> 32))',
                   'back_chunk_serial[chunk] = serial',
                   'rel_render |= (rel_mask[RelRender][chunk] & mask)',
                   'rel_color |= (rel_mask[RelColor][chunk] & mask)'):
        if marker not in code:
            raise ValueError('PC #308 register mask invariant lost: '+marker)
    liverpool.write_text(code)
    print('SotC PC #308 depth/G-buffer fastpaths: ARM64 exact 32-bit register deltas + YIELD preserved')


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--gpu',type=Path,required=True)
    patch(p.parse_args().gpu)
