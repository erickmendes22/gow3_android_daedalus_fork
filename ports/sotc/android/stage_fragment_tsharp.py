#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC-only Android fragment texture-descriptor array fix.

The original PC workaround recognizes dynamic TSharp tables in compute only.
It deliberately excludes vertex (SotC VS 0x9d6f9bf4 hung the GPU).
On Android the same table resolution is also needed for fragment shaders
using runtime-indexed textures/samplers; keep vertex exclusion intact.
"""
from pathlib import Path


def patch_fragment_tsharp(gpu: Path) -> None:
    path = gpu / "shadps4/shader_recompiler/ir/passes/resource_patching_pass.cpp"
    src = path.read_text()
    anchor = '''    // Per-game (Pink-shadPS4): a sampled T# read at a dynamic offset becomes a descriptor array.
    // Compute only: SotC's vs 0x9d6f9bf4 matches too (shadow map tables) and hung the GPU with it
    const u32 array_size = info.hw_stage == HwStage::Compute ? DynamicTsharpArraySize() : 0;'''
    replacement = '''    // SotC Android: resolve runtime-indexed TSharp tables for fragment
    // materials/lighting as well as compute. Keep the vertex exclusion:
    // SotC VS 0x9d6f9bf4 previously hung the GPU with descriptor arrays.
    // Reuse the proven PC affine matcher, null out-of-bounds binding and
    // max-descriptor checks; never translate unmatched runtime sources into
    // made-up fixed descriptor offsets.
#ifdef __ANDROID__
    static const bool android_fragment_tsharp = [] {
        const char* v = std::getenv("SOTC_ANDROID_FRAGMENT_TSHARP");
        return !v || v[0] != '0';
    }();
    const bool fragment_table =
        android_fragment_tsharp && info.hw_stage == HwStage::Fragment;
#else
    constexpr bool fragment_table = false;
#endif
    const u32 array_size =
        (info.hw_stage == HwStage::Compute || fragment_table)
            ? DynamicTsharpArraySize() : 0;'''
    if src.count(anchor) != 1:
        raise ValueError(f"SotC fragment TSharp: expected one PC source anchor, found {src.count(anchor)}")
    src = src.replace(anchor, replacement, 1)
    assert "MatchSharpTable(resource.sharps[0])" in src
    assert "NumArrayDescriptors(info) + array_size + 1" in src
    assert "ir.ImageArrayHandle" in src
    assert "SotC VS 0x9d6f9bf4 previously hung" in src
    src = src.replace("#include <limits>\n", "#include <cstdlib>\n#include <limits>\n", 1)
    path.write_text(src)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", type=Path, required=True)
    args = p.parse_args()
    patch_fragment_tsharp(args.gpu)
