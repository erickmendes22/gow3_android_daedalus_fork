#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC Android: use upstream's real barycentric GS fallback on Adreno.

SotC fragment shaders manually interpolate vertex attributes using barycentrics.
The Adreno 830 Turnip build lacks VK_KHR_fragment_shader_barycentric and
VK_AMD_shader_explicit_vertex_parameter. The PC renderer already generates a
pass-through GS with the required values, but inexplicably gates it to NVIDIA.
Do NOT fake capabilities: only use it if the Vulkan geometryShader feature
is actually reported. Preserve NVIDIA, and all non-Android, behavior.
"""
from pathlib import Path


def patch_adreno_barycentric_gs(gpu: Path) -> None:
    path = gpu/"shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp"
    src = path.read_text()
    old = '''    const bool barycentric_via_gs = !khr_barycentric && !amd_explicit_vertex &&
                                    instance.IsGeometryStageSupported() &&
                                    instance.GetDriverID() == vk::DriverId::eNvidiaProprietary &&
                                    !env_is("SOTC_BARYCENTRIC_GS", "0");'''
    new = '''    // Adreno/Turnip lacks both direct barycentric extensions. Without this
    // fallback SotC's per-vertex fragment inputs are not interpolated:
    // missing materials, untextured geometry and incorrect lighting/fog.
    // Reuse the upstream GS fallback, always gated on Vulkan geometryShader.
    // Keep every other platform's NVIDIA-only policy unchanged.
#ifdef __ANDROID__
    const bool adreno_missing_barycentrics = instance.GetVendorID() == 0x5143;
#else
    constexpr bool adreno_missing_barycentrics = false;
#endif
    const bool barycentric_via_gs = !khr_barycentric && !amd_explicit_vertex &&
                                    instance.IsGeometryStageSupported() &&
                                    (instance.GetDriverID() == vk::DriverId::eNvidiaProprietary ||
                                     adreno_missing_barycentrics) &&
                                    !env_is("SOTC_BARYCENTRIC_GS", "0");
#ifdef __ANDROID__
    if (instance.GetVendorID() == 0x5143) {
        std::fprintf(stderr,
                     "SotC Adreno barycentric: KHR=%d AMD=%d geometryShader=%d "
                     "GS_fallback=%d\\n",
                     int(khr_barycentric), int(amd_explicit_vertex),
                     int(instance.IsGeometryStageSupported()), int(barycentric_via_gs));
    }
#endif'''
    if src.count(old) != 1:
        raise ValueError("SotC Adreno barycentric: NVIDIA-only fallback anchor missing")
    src = src.replace(old,new)
    # This is not a new shader implementation. The upstream renderer already
    # generates, serializes and binds the auxiliary GS for triangle pipelines.
    for symbol in ("GraphicsPipeline::SerializationSupport::with_gs = barycentric_via_gs;",
                   ".supports_fragment_shader_barycentric = khr_barycentric || barycentric_via_gs,",
                   ".barycentric_via_gs = barycentric_via_gs,"):
        if symbol not in src:
            raise ValueError(f"Missing upstream barycentric integration: {symbol}")
    path.write_text(src)


if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--gpu",type=Path,required=True)
    a=p.parse_args()
    patch_adreno_barycentric_gs(a.gpu)
