#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Restore LDS synchronization for the 64-lane Adreno shader profile.

The pinned SotC renderer enables shared-memory barriers for subgroups <64,
NVIDIA and AMD64, but excludes Qualcomm 64-wide shaders. On Android Turnip,
Wave32 already receives these barriers; switching to Wave64 silently removes
them. Synchronization is correctness-critical for SotC's LDS reductions.
Only the staged Android renderer is changed, never the PC upstream.
"""
from pathlib import Path


def patch_adreno_lds_integrity(gpu: Path) -> None:
    path = gpu / "shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp"
    source = path.read_text()
    before = """        .needs_lds_barriers = instance.GetDriverID() == vk::DriverId::eNvidiaProprietary ||
                              instance.GetDriverID() == vk::DriverId::eMesaKosmickrisp ||
                              instance.SubgroupSize() < 64 || amd64_lds,"""
    after = """        // SotC Android/Turnip: Wave32 gets LDS barriers through the <64
        // condition, but the same GPU on Wave64 did not. The missing workgroup
        // memory synchronization can leave geometry/material intermediate
        // values undefined. This vendor path changes only Adreno Wave64:
        // Wave32, AMD and NVIDIA retain their previous policy.
        .needs_lds_barriers = instance.GetDriverID() == vk::DriverId::eNvidiaProprietary ||
                              instance.GetDriverID() == vk::DriverId::eMesaKosmickrisp ||
                              instance.SubgroupSize() < 64 || amd64_lds ||
                              instance.GetVendorID() == 0x5143,"""
    if source.count(before) != 1:
        raise ValueError("SotC Adreno LDS: expected exact upstream barrier policy once")
    path.write_text(source.replace(before, after, 1))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", required=True, type=Path)
    patch_adreno_lds_integrity(parser.parse_args().gpu)
