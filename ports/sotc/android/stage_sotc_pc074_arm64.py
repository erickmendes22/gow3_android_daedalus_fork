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
    # PC #308 introduced new x86 TSC diagnostics in EOP, depth and
    # dispatch profiling. Their opt-in nature does not make the C++ builtin
    # valid on AArch64, even when disabled at runtime. Use the already
    # ported SotcStats::Ticks() (cntvct_el0) for consistent hardware ticks.
    stats_path=root/'sotc_stats.h'
    stats=stats_path.read_text()
    tick_def='inline uint64_t Ticks() {'
    if stats.count(tick_def) != 1:
        raise ValueError('PC #308 ARM64 tick helper absent')
    prefix,suffix=stats.split(tick_def,1)
    old='__builtin_ia32_rdtsc()'
    if prefix.count(old) != 4:
        raise ValueError(f'PC #308 TSC diagnostic call-site drift ({prefix.count(old)})')
    prefix=once(prefix,'inline double TicksPerMs() {',
                'inline uint64_t Ticks();\ninline double TicksPerMs() {',
                'forward declaration for portable profiling clock')
    prefix=prefix.replace(old,'Ticks()')
    stats_path.write_text(prefix+tick_def+suffix)

    arm_now='''#if defined(__aarch64__)
    u64 ticks;
    __asm__ __volatile__("mrs %0, cntvct_el0" : "=r"(ticks));
    return ticks;
#else
    return __builtin_ia32_rdtsc();
#endif'''
    draw_path=root/'renderer_vulkan/vk_rasterizer.h'
    draw=draw_path.read_text()
    draw=once(draw,'inline u64 Now() {\n    return __builtin_ia32_rdtsc();\n}',
              'inline u64 Now() {\n'+arm_now+'\n}',
              'ARM64 depth/G-buffer draw profiling clock')
    draw_path.write_text(draw)
    dispatch_path=root/'renderer_vulkan/sotc_dispphase.h'
    dispatch=dispatch_path.read_text()
    dispatch=once(dispatch,'inline uint64_t Now() {\n    return __builtin_ia32_rdtsc();\n}',
                  'inline uint64_t Now() {\n'+arm_now.replace('    u64 ticks;', '    uint64_t ticks;')+'\n}',
                  'ARM64 dispatch phase profiling clock')
    dispatch_path.write_text(dispatch)

    # AArch64 NDK defines u64 as unsigned long, while strtoull returns
    # unsigned long long. PC's no-trailing-return-type lambda mixes distinct
    # return types; a width-correct cast preserves all 64 bits on Android.
    image_path=root/'texture_cache/image.cpp'
    image=image_path.read_text()
    image=once(image,
               'return t ? std::strtoull(t, nullptr, 10) : u64{2048} * 2048;',
               'return t ? static_cast<u64>(std::strtoull(t, nullptr, 10)) : u64{2048} * 2048;',
               'PC dedicated image size type parity on ARM64')
    image_path.write_text(image)

    # PC #339 copies from the guest address under a custom Windows fault
    # recovery guard (bb_setjmp, bb_copy_guard_buf), and explicitly calls
    # Win32 PrefetchVirtualMemory. On Android that guard's ABI does not exist:
    # retain only the original mapped backing-view copy (always tracked and
    # readback-safe), never skip a guest byte or use a mismatched sigjmp_buf.
    shim_path=gpu/'shim/bbgpu.cpp'
    shim=shim_path.read_text()
    shim=once(shim,
              'extern "C" __thread std::uintptr_t bb_copy_guard_lo, bb_copy_guard_hi;',
              '#if !defined(__ANDROID__)\nextern "C" __thread std::uintptr_t bb_copy_guard_lo, bb_copy_guard_hi;',
              'guard proprietary guest-copy recovery declarations')
    shim=once(shim,
              '    return true;\n}\nstatic void CopySparseSerial(VAddr source, u8* dest, u64 size) {',
              '    return true;\n}\n#endif // !__ANDROID__: PC guest view fault guard\nstatic void CopySparseSerial(VAddr source, u8* dest, u64 size) {',
              'end of PC guest view fault guard')
    shim=once(shim,
              '        if (backing && prefetch && n >= 256 * 1024) {',
              '#if !defined(__ANDROID__)\n        if (backing && prefetch && n >= 256 * 1024) {',
              'Win32 prefetch host-only guard')
    shim=once(shim,
              '            PrefetchVirtualMemory(GetCurrentProcess(), 1, &range, 0);\n        }',
              '            PrefetchVirtualMemory(GetCurrentProcess(), 1, &range, 0);\n        }\n#endif',
              'Win32 prefetch boundary')
    shim=once(shim,
              '        } else if (backing && kCopyGuestView) {',
              '#if !defined(__ANDROID__)\n        } else if (backing && kCopyGuestView) {',
              'Windows speculative copy fallback condition')
    shim=once(shim,
              '                std::memcpy(dest, backing, n);\n            }\n        } else if (backing) std::memcpy(dest, backing, n);',
              '                std::memcpy(dest, backing, n);\n            }\n#endif\n        } else if (backing) std::memcpy(dest, backing, n);',
              'Android backing-view copy remains complete')
    shim_path.write_text(shim)

    liverpool.write_text(code)
    print('SotC PC #308 depth/G-buffer fastpaths: ARM64 exact 32-bit register deltas + YIELD preserved')


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--gpu',type=Path,required=True)
    patch(p.parse_args().gpu)
