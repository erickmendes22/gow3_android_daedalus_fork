#!/usr/bin/env python3
"""PC v0.72 large staging reuse, strictly opt-in and host-only on Android.

The 0.1.46 renderer already rounds deferred GPU readbacks up to powers of
two. For non-deferred host-visible uploads (<=64 MiB), v0.1.47 can use the
same size classes, avoiding repeated allocations for slightly different
streaming sizes. DeviceLocal/VRAM, deferred readbacks, and >64 MiB uploads
retain the exact original allocation rules. Never skip a required copy.
"""
from pathlib import Path


def patch_host_large_pow2(gpu: Path) -> None:
    path = Path(gpu) / "shadps4/video_core/renderer_vulkan/vk_staging_buffer_pool.cpp"
    source = path.read_text()
    old = """    const u64 alloc_size =
        deferred ? std::bit_ceil(std::max(size, LARGE_MIN_GRANULARITY)) : RoundAllocationSize(size);
    const u64 max_size = deferred ? alloc_size : std::max(size + size / 4, RoundAllocationSize(size));"""
    new = """    // SotC Android opt-in: reuse host-visible large upload buffers in
    // power-of-two classes. Never change DeviceLocal VRAM or GPU readbacks.
    // Cap the classing to <=64 MiB uploads to avoid inflating huge uploads.
    static const bool sotc_host_large_pow2 = [] {
        const char* v = std::getenv("SOTC_HOST_LARGE_POW2");
        return v && v[0] == '1';
    }();
    const bool host_pow2 = sotc_host_large_pow2 && !deferred &&
                           type != MemoryType::DeviceLocal && size <= 64_MB;
    const u64 alloc_size = (deferred || host_pow2)
        ? std::bit_ceil(std::max(size, LARGE_MIN_GRANULARITY))
        : RoundAllocationSize(size);
    const u64 max_size = deferred ? alloc_size
        : host_pow2 ? alloc_size * 2
                    : std::max(size + size / 4, RoundAllocationSize(size));"""
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"SotC host large staging source changed ({count} matches)")
    path.write_text(source.replace(old, new))
    print("SotC PC 0.72 host large staging: opt-in, <=64MiB, nondeferred, never VRAM")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", type=Path, required=True)
    patch_host_large_pow2(parser.parse_args().gpu)
