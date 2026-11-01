#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC Android: do not fast-reuse descriptors while skipping resource hazards.

On a FAST_BIND cache hit the PC renderer returns from BindResources before
BindTextures/BindBuffers. The previous ResetBindings has already cleared its
bound_images and bound_buffers. This means that the next draw can miss image
transitions, buffer access tracking, texture streaming/LOD sampling and rebinds
if any sampled resource changed while the descriptor hash stayed the same.

Only pipelines without buffer/image/sampler resources remain eligible for
FAST_BIND. The exact guest draw, Vulkan sync and descriptor binding paths
are unchanged for resources, preserving correctness without blanket disabling
CPU optimizations or all the other shader-cache work.
"""
from pathlib import Path


def patch_resource_coherence(gpu: Path) -> None:
    path = gpu / "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
    src = path.read_text()
    a = src.find("bool Rasterizer::FastBindEligible(")
    b = src.find("\nu64 Rasterizer::FastBindHash(", a)
    if a < 0 or b <= a:
        raise ValueError("SotC resource coherence: FAST_BIND source changed")
    part = src[a:b]
    before = """        if (stage->has_storage_images || !stage->fmasks.empty()) {
            return false;
        }"""
    after = """#ifdef __ANDROID__
        // A fast-bind hit skips BindTextures/BindBuffers for this draw, but
        // ResetBindings already clears bound_images/bound_buffers after the
        // preceding draw. Never skip image layout transitions, LOD marking,
        // resource invalidation, barriers or GPU read tracking on Android.
        // Keep FAST_BIND for truly descriptor-free graphics pipelines.
        if (!stage->images.empty() || !stage->buffers.empty() ||
            !stage->samplers.empty() || !stage->fmasks.empty()) {
            return false;
        }
#endif
        if (stage->has_storage_images || !stage->fmasks.empty()) {
            return false;
        }"""
    if part.count(before) != 1:
        raise ValueError("SotC resource coherence: expected exact eligibility guard")
    required = (
        "fast_bind_hit = true;",
        "return true;",
        "BindTextures(*stage, binding);",
        "BindBuffers(*stage, binding, push_data);",
        "bound_images.clear();",
        "bound_buffers.clear();",
        "void Rasterizer::ResetBindings(bool is_compute)",
    )
    for needle in required:
        if needle not in src:
            raise ValueError(f"SotC resource coherence: missing semantic guard {needle}")
    src = src[:a] + part.replace(before, after, 1) + src[b:]
    path.write_text(src)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", type=Path, required=True)
    patch_resource_coherence(parser.parse_args().gpu)
