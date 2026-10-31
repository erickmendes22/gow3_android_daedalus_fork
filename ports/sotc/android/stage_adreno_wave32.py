#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC-only optional Adreno Wave32 path; never changes PC/GoW3 renderer."""
from pathlib import Path

def swap(s, a, b, label):
    count=s.count(a)
    if count != 1:
        raise ValueError(f"SotC wave32 staging {label}: expected once, found {count}")
    return s.replace(a,b)

def patch_adreno_wave32(gpu: Path) -> None:
    # The SotC PC port has a proven 32-lane lowering for devices that
    # cannot pin a 64-wide subgroup in every graphics+compute stage.
    # Turnip on Adreno reports 32..64, can pin all stages, yet the driver's
    # 64-lane output may be incorrect in some post-processing shaders.
    # This mode pins all three stages to 32 and matches the recompiler
    # target size, rather than silently mixing 32/64 shader groups.
    path=gpu/"shadps4/video_core/renderer_vulkan/vk_instance.h"
    text=path.read_text()
    text=swap(text,'''    bool IsSubgroupSize64Supported() const {''',
    '''    bool UseAdrenoWave32() const {
#ifdef __ANDROID__
        const char* requested = std::getenv("SOTC_ADRENO_WAVE32");
        if (!requested || requested[0] != '1' || GetVendorID() != 0x5143)
            return false;
        constexpr auto stages = vk::ShaderStageFlagBits::eVertex |
                                vk::ShaderStageFlagBits::eFragment |
                                vk::ShaderStageFlagBits::eCompute;
        return vk13_features.subgroupSizeControl &&
               vk13_props.minSubgroupSize <= 32 && vk13_props.maxSubgroupSize >= 32 &&
               (vk13_props.requiredSubgroupSizeStages & stages) == stages;
#else
        return false;
#endif
    }

    bool IsSubgroupSize64Supported() const {
        if (UseAdrenoWave32()) return false;''',
    "force 32 across all available stages instead of mixing profile/pipeline")
    text=swap(text,'''    u32 RequiredSubgroupSize(vk::ShaderStageFlagBits stage) const {
        if (IsSubgroupSize64Supported()) {''',
    '''    u32 RequiredSubgroupSize(vk::ShaderStageFlagBits stage) const {
        if (UseAdrenoWave32()) return 32u;
        if (IsSubgroupSize64Supported()) {''',
    "required graphics/compute subgroup size")
    text=swap(text,'''    u32 SubgroupSize() const {
        if (IsSubgroupSize64Supported()) {''',
    '''    u32 SubgroupSize() const {
        if (UseAdrenoWave32()) return 32u;
        if (IsSubgroupSize64Supported()) {''',
    "shader compiler profile subgroup size")
    path.write_text(text)

    # A boot log must positively identify whether the requested mode was
    # really accepted by Vulkan capabilities. One can then A/B two modes
    # without guessing whether Turnip ignored the subgroup request.
    path=gpu/"shadps4/video_core/renderer_vulkan/vk_instance.cpp"
    text=path.read_text()
    # vk13_features is assigned after the early "GPU subgroups" log. Checking
    # UseAdrenoWave32() there *always* reported false for a freshly initialized
    # device, although pipeline compilation could subsequently request 32 lanes.
    # Log the actual pipeline subgroup policy only after vk13_features is set.
    old='''    vk13_features = feature_chain.get<vk::PhysicalDeviceVulkan13Features>();'''
    new='''    vk13_features = feature_chain.get<vk::PhysicalDeviceVulkan13Features>();
    std::fprintf(stderr,
                 "SotC Adreno Wave32 effective: %s (requested=%s, vendor=%#x; "
                 "compiler=%u, vertex=%u, fragment=%u, compute=%u, physical=%u)\\n",
                 UseAdrenoWave32() ? "active" : "inactive",
                 std::getenv("SOTC_ADRENO_WAVE32") ? std::getenv("SOTC_ADRENO_WAVE32") : "0",
                 GetVendorID(), SubgroupSize(),
                 RequiredSubgroupSize(vk::ShaderStageFlagBits::eVertex),
                 RequiredSubgroupSize(vk::ShaderStageFlagBits::eFragment),
                 RequiredSubgroupSize(vk::ShaderStageFlagBits::eCompute),
                 vk11_props.subgroupSize);'''
    text=swap(text,old,new,"log effective waveform after Vulkan feature initialization")
    path.write_text(text)
