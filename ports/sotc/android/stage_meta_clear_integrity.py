#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC Android: never suppress a multi-output compute dispatch as a metadata clear.

The original heuristic calls TextureCache::ClearMeta(address) on the first
metadata-address write and returns true, dropping the ENTIRE dispatch. A real
compute shader that also writes another buffer or image loses those writes.
Preserve the original PC path and the existing true metadata-clear fast path.
Only guard the Android staged renderer; no shader/LOD/TAA policy changes.
"""
from pathlib import Path


def patch_meta_clear_integrity(gpu: Path) -> None:
    path = gpu / "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
    text = path.read_text()
    old = """    if (!info.has_bitwise_xor) {
        // Assume if a shader writes metadata without address calculation, it is a clear shader."""
    new = """#ifdef __ANDROID__
    // Clearing the virtual metadata flag can replace an entire compute dispatch
    // ONLY if metadata is its single output. Previously a metadata address in
    // any writable buffer caused every other buffer/image write to be LOST.
    // This can leave the G-buffer or streamed image inputs uninitialized.
    bool metadata_only_dispatch = info.images.empty();
    u32 non_special_writes = 0;
    for (const auto& desc : info.buffers) {
        if (!desc.is_written) {
            continue;
        }
        if (desc.IsSpecial() || ++non_special_writes > 1) {
            metadata_only_dispatch = false;
            break;
        }
    }
    metadata_only_dispatch &= non_special_writes == 1;
#else
    constexpr bool metadata_only_dispatch = true;
#endif
    if (!info.has_bitwise_xor && metadata_only_dispatch) {
        // Assume if a shader writes metadata without address calculation, it is a clear shader."""
    if text.count(old) != 1:
        raise ValueError(f"SotC metadata clear: expected one exact original heuristic, got {text.count(old)}")
    if "texture_cache.ClearMeta(address)" not in text:
        raise ValueError("SotC metadata clear: original metadata tracking is missing")
    path.write_text(text.replace(old, new, 1))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", required=True, type=Path)
    patch_meta_clear_integrity(parser.parse_args().gpu)
