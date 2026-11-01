#!/usr/bin/env python3
"""Assemble an Android/Bionic development tree without changing upstream source.

Source-of-truth for game HLE/renderer remains JulioCacko/The-Order-1886_pc.
This script only overlays the explicitly modified Android CPU-boundary files.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess

UPSTREAM = "c53cd01d032995fe622033623ab64b4cf6b02233"
DONOR = "b3a7c3d5e916cf8f4622192c0faa9383ebd77c00"
FILES = [
    "src/probe.c", "src/runtime.c", "src/runtime.h", "src/runtime_thread.c",
    "src/guest_cpu.h", "src/runtime_cpu.c", "src/runtime_audio.c",
    "src/runtime_audio_bionic.c", "src/runtime_pad.c", "src/runtime_pad_bionic.c",
    "src/vulkan_smoke.c",
    "cpu/guest_cpu_fex.cpp",
    "cpu/host_call_arm64.S", "cpu/bionic_compat.h",
    "cpu/fex_project.cmake", "cpu/order1886cpu.cmake",
    "gpu/CMakeLists.txt",
    "gpu/shim/sdl_window.h",
    "gpu/shim/ps4gpu.cpp",
    "gpu/shim/window_android.cpp",
    "gpu/shim/order1886_present_client.cpp",
    "gpu/shim/order1886_present_client.h",
    "gpu/shim/vk_driver_loader.cpp",
    "gpu/shim/vk_driver_loader.h",
    "gpu/shim/vk_forwarders.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_swapchain.h",
    "gpu/shadps4/video_core/renderer_vulkan/vk_swapchain.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_swapchain_ahb.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_swapchain_ahb.h",
    "gpu/shadps4/video_core/renderer_vulkan/vk_ahb_acquire_wait.h",
    "gpu/shadps4/video_core/buffer_cache/region_manager.h",
    "gpu/shadps4/video_core/page_manager.cpp",
    "gpu/shadps4/common/signal_context.cpp",
    "gpu/shadps4/common/arch.h", "gpu/shim/ps4_threads.h",
    "gpu/shadps4/video_core/renderer_vulkan/vk_bind_helper.h",
    "gpu/shadps4/video_core/renderer_vulkan/vk_draw_pipe.h",
    "gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp",
    "gpu/shim/window.cpp", "gpu/shim/ps4_write_log.cpp",
    "gpu/shim/gow3_copy.h",
    "gpu/shim/gow3_copy.cpp",
    "gpu/shim/gow3_toggles.h",
    "gpu/shim/gow3_threads.h",
    "gpu/shadps4/video_core/buffer_cache/copy_ranges.h",
    "gpu/shadps4/video_core/buffer_cache/memory_tracker.h",
    "gpu/shadps4/video_core/renderer_vulkan/driver_cache_file.h",
    "gpu/shadps4/shader_recompiler/profile.h",
    "gpu/shadps4/shader_recompiler/runtime_info.h",
    "gpu/shadps4/shader_recompiler/frontend/translate/vector_interpolation.cpp",
    "gpu/shadps4/shader_recompiler/backend/spirv/emit_spirv_per_vertex.cpp",
    "gpu/shadps4/shader_recompiler/backend/spirv/emit_spirv_per_vertex.h",
    "gpu/shadps4/shader_recompiler/backend/spirv/spirv_emit_context.cpp",
    "gpu/shadps4/shader_recompiler/backend/spirv/emit_spirv_context_get_set.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_draw_prep.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_graphics_pipeline.cpp",
    "gpu/shadps4/shader_recompiler/recompiler.cpp",
    "gpu/shadps4/shader_recompiler/info.h",
    "gpu/shadps4/video_core/buffer_cache/buffer_cache.h",
    "gpu/shadps4/video_core/buffer_cache/buffer_cache.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.h",
    "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.h",
    "gpu/shadps4/shader_recompiler/ir/passes/srt.h",
    "gpu/shadps4/shader_recompiler/ir/passes/flatten_extended_userdata_pass.cpp",
    "gpu/shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc",
    "gpu/shadps4/shader_recompiler/ir/passes/srt.h",
    "gpu/shadps4/shader_recompiler/ir/passes/srt_arm64.h",
    "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp",
    "gpu/shadps4/video_core/renderer_vulkan/vk_platform.cpp",
    "tools/android/present/order1886_present_proto.h",
    "gpu/shim/ps4_overlay.cpp",
    "tools/android/bionic/present/order1886present.c",
    "tools/android/bionic/present/geometry.h",
    "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/Order1886Present.java",
    "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/Order1886PadBridge.java",
    "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/Order1886AudioBridge.java",
]


def patch_headless_imgui(output: Path) -> None:
    """The Android AHB presenter never creates a VkSurfaceKHR or a VkSwapchainKHR.

    Dear ImGui's generic Vulkan function table nevertheless tries to load WSI
    helper commands. A direct Turnip HAL cannot return commands for device
    extensions that were not enabled; they are unnecessary for our renderer.
    Keep every core command mandatory and diagnose a genuinely missing one.
    """
    file = output / "gpu/third_party/imgui/backends/imgui_impl_vulkan.cpp"
    src = file.read_text(encoding="utf-8")
    marker = "bool    ImGui_ImplVulkan_LoadFunctions("
    if src.count(marker) != 1:
        raise RuntimeError("Pinned ImGui Vulkan function loader changed; refuse patch")
    headless = """#ifdef __ANDROID__
static bool Order1886OptionalHeadlessWsi(const char* name)
{
    return strcmp(name, "vkCreateSwapchainKHR") == 0 ||
           strcmp(name, "vkDestroySwapchainKHR") == 0 ||
           strcmp(name, "vkGetSwapchainImagesKHR") == 0 ||
           strcmp(name, "vkDestroySurfaceKHR") == 0 ||
           strcmp(name, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR") == 0 ||
           strcmp(name, "vkGetPhysicalDeviceSurfaceFormatsKHR") == 0 ||
           strcmp(name, "vkGetPhysicalDeviceSurfacePresentModesKHR") == 0;
}
#else
static bool Order1886OptionalHeadlessWsi(const char*) { return false; }
#endif

"""
    src = src.replace(marker, headless + marker)
    old = "    if (func == nullptr)   " + chr(92) + chr(10) + "        return false;"
    new = ("    if (func == nullptr && !Order1886OptionalHeadlessWsi(#func)) { " + chr(92) + chr(10) +
           '        fprintf(stderr, "The Order: ImGui required Vulkan function missing: %s\\n", #func); ' + chr(92) + chr(10) +
           "        return false; " + chr(92) + chr(10) + "    }")
    if src.count(old) != 1:
        raise RuntimeError("Pinned ImGui Vulkan macro changed; refuse patch")
    src = src.replace(old, new)
    file.write_text(src, encoding="utf-8")

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="The Order PC checkout")
    parser.add_argument("--output", type=Path, required=True, help="New, separate staging directory")
    parser.add_argument("--overlay", type=Path, default=Path(__file__).resolve().parents[1] / "overlay")
    parser.add_argument("--allow-other-revision", action="store_true")
    args = parser.parse_args()
    source, output, overlay = (v.expanduser().resolve() for v in (args.source,args.output,args.overlay))
    if not (source / "src/probe.c").is_file() or not (source / "gpu/CMakeLists.txt").is_file():
        parser.error("Expected a complete The Order PC source checkout")
    if output == source or source in output.parents or output in source.parents:
        parser.error("Refusing to overwrite or stage inside the upstream tree")
    if output.exists():
        parser.error("Output directory exists; never overlay a potentially modified tree")
    if not args.allow_other_revision:
        sha = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],text=True).strip()
        if sha != UPSTREAM:
            parser.error(f"Source revision {sha} is not the verified {UPSTREAM}; use --allow-other-revision deliberately")
    for path in FILES:
        if not (overlay / path).is_file():
            parser.error(f"Missing Android overlay: {path}")
    shutil.copytree(source,output,symlinks=True,ignore=shutil.ignore_patterns(".git","out","user","__pycache__","*.pyc"))
    for path in FILES:
        dest=output/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(overlay/path,dest)
    patch_headless_imgui(output)
    meta={
        "project":"The Order: 1886 Android Bionic (development only)",
        "upstream_repository":"JulioCacko/The-Order-1886_pc",
        "upstream_sha":UPSTREAM,
        "android_cpu_donor":"erickmendes22/gow3_android_daedalus_fork",
        "donor_sha":DONOR,
        "overlaid_files":FILES,
        "build_verified":False,
        "android_gameplay_verified":False,
    }
    (output/"ANDROID_PORT_MANIFEST.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf-8")
    print(f"Assembled {output}; {len(FILES)} CPU/Vulkan overlay files. GPU linking and presentation need device validation.")

if __name__=="__main__":
    run()
