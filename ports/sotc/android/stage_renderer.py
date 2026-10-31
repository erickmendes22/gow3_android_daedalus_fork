#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prepare original SotC Vulkan renderer for Android in an isolated build tree."""
import argparse
from pathlib import Path
import shutil

def swap(text,old,new,label):
    if text.count(old)!=1:
        raise ValueError(f'Upstream changed: {label}')
    return text.replace(old,new)

def stage(upstream,out,android_window):
    gpu=upstream.resolve()/'gpu'
    out=out.resolve()
    if not (gpu/'CMakeLists.txt').exists() or not (gpu/'shadps4').is_dir():
        raise ValueError('Original SotC GPU sources not found')
    if out==gpu or out in gpu.parents or gpu in out.parents:
        raise ValueError('Refusing to overwrite upstream renderer')
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(gpu,out,symlinks=True,ignore=shutil.ignore_patterns('.git','out','build'))
    c=out/'CMakeLists.txt'
    t=c.read_text()
    t=swap(t,'find_package(Vulkan REQUIRED)',
"""if(ANDROID)
    find_package(VulkanHeaders CONFIG REQUIRED)
    add_library(Vulkan::Vulkan INTERFACE IMPORTED)
    set_target_properties(Vulkan::Vulkan PROPERTIES INTERFACE_LINK_LIBRARIES "Vulkan::Headers;vulkan")
else()
    find_package(Vulkan REQUIRED)
endif()""",'Vulkan')
    t=swap(t,'pkg_check_modules(SDL3 REQUIRED IMPORTED_TARGET sdl3)\nif (NOT WIN32)\n    pkg_check_modules(X11 REQUIRED IMPORTED_TARGET x11)\nendif()',
"""if(ANDROID)
    add_library(PkgConfig::SDL3 INTERFACE IMPORTED)
    add_library(PkgConfig::X11 INTERFACE IMPORTED)
else()
    pkg_check_modules(SDL3 REQUIRED IMPORTED_TARGET sdl3)
    if (NOT WIN32)
        pkg_check_modules(X11 REQUIRED IMPORTED_TARGET x11)
    endif()
endif()""",'SDL3/X11')
    t=swap(t,'file(GLOB SHIM_SOURCES CONFIGURE_DEPENDS shim/*.cpp shim/*/*.cpp sotc/*.cpp)',
"""file(GLOB SHIM_SOURCES CONFIGURE_DEPENDS shim/*.cpp shim/*/*.cpp sotc/*.cpp)
if(ANDROID)
    # These patchers emit native x86 machine code through Xbyak. The guest
    # is translated by FEX on AArch64; never execute x86 patch stubs natively.
    list(FILTER SHIM_SOURCES EXCLUDE REGEX "shim/window\\.cpp$|/sotc/cpu_patches\\.cpp$|/sotc/sotc_patches\\.cpp$")
endif()""",'window')
    t=swap(t,'target_link_libraries(bbgpu PUBLIC Vulkan::Headers fmt::fmt Boost::headers magic_enum::magic_enum',
"""if(ANDROID)
    set(SOTC_FMT_TARGET fmt::fmt-header-only)
else()
    set(SOTC_FMT_TARGET fmt::fmt)
endif()
target_link_libraries(bbgpu PUBLIC Vulkan::Headers ${SOTC_FMT_TARGET} Boost::headers magic_enum::magic_enum""",'fmt')
    # Desktop test executables depend on ../tests, which is intentionally
    # absent in this separate Android renderer staging directory.
    # Keep bbgpu and shader generation enabled; only host test targets skip.
    t=swap(t,'# Explicit test targets; neither launches the game nor needs a Vulkan device.',
           '# Explicit test targets; neither launches the game nor needs a Vulkan device.\nif(NOT ANDROID)',
           'host test targets')
    t+='\nendif() # NOT ANDROID (desktop GPU tests)\n'
    t+="""
if(ANDROID)
    target_compile_definitions(bbgpu PRIVATE VK_USE_PLATFORM_ANDROID_KHR)
    target_link_libraries(bbgpu PRIVATE nativewindow android log dl)
    # FFmpeg's Android NEON assembly uses direct ADRP references to global
    # fft tables. Hide symbols from the statically linked FFmpeg archives in
    # this shared object, so AArch64 resolves those references locally.
    # The NDK toolchain adds --no-undefined to every shared library. SotC's
    # renderer deliberately imports runtime_* from the native FEX main
    # executable, which exports them with --export-dynamic. Override that
    # linker restriction only for bbgpu, and check each unresolved runtime_*
    # against the real executable in verify_sotc_link.py before packaging.
    # -z undefs cancels the earlier NDK --no-undefined/-z defs in LLD.
    target_link_options(bbgpu PRIVATE
        "-Wl,--exclude-libs,libavformat.a:libavcodec.a:libavutil.a:libswscale.a:libswresample.a"
        "-Wl,-z,undefs")
endif()
"""
    c.write_text(t)
    shutil.copy2(android_window,out/'shim/window_android.cpp')
    # Streamline DLSS frame generation (DXGI DLLs) is Windows-only. Keep
    # the SotC Vulkan shader/texture core, replace only optional frame-gen
    # adapters with explicit Android implementations (not silent fallbacks).
    renderer=out/'shadps4/video_core/renderer_vulkan'
    root=Path(__file__).resolve().parents[3]
    shutil.copy2(root/'ports/sotc/android/vk_dlssg_android.cpp',
                 renderer/'vk_dlssg_android.cpp')
    shutil.copy2(root/'ports/sotc/android/vk_framegen_android.cpp',
                 renderer/'vk_framegen_android.cpp')
    c=out/'CMakeLists.txt'
    cmake=c.read_text()
    cmake=swap(cmake,r'list(FILTER VIDEO_CORE EXCLUDE REGEX "renderdoc\\.cpp$")',
r"""list(FILTER VIDEO_CORE EXCLUDE REGEX "renderdoc\\.cpp$")
if(ANDROID)
    list(FILTER VIDEO_CORE EXCLUDE REGEX "/vk_dlssg\\.cpp$|/vk_framegen\\.cpp$")
endif()""",'exclude desktop-only DXGI source')
    c.write_text(cmake)

    s=out/'shim/bbgpu.cpp'
    text=s.read_text()
    text=swap(text,'#include <SDL3/SDL.h>',
              '#ifndef __ANDROID__\n#include <SDL3/SDL.h>\n#endif','SDL include')
    text=swap(text,'const SDL_DisplayMode* mode = SDL_GetCurrentDisplayMode(SDL_GetPrimaryDisplay());\n        const u32 rate = mode && mode->refresh_rate > 0 ? u32(mode->refresh_rate + 0.5f) : 60;',
              '#ifdef __ANDROID__\n        const u32 rate = 60;\n#else\n        const SDL_DisplayMode* mode = SDL_GetCurrentDisplayMode(SDL_GetPrimaryDisplay());\n        const u32 rate = mode && mode->refresh_rate > 0 ? u32(mode->refresh_rate + 0.5f) : 60;\n#endif','display')
    text=text.replace('SDL_Delay(2);','std::this_thread::sleep_for(std::chrono::milliseconds(2));')
    text=text.replace('SDL_Delay(50);','std::this_thread::sleep_for(std::chrono::milliseconds(50));')
    s.write_text(text)

    # SotC's x86-only timing and spin instructions must be translated when
    # building native aarch64. Keep both original fast paths on desktop.
    stats=out/'shadps4/video_core/sotc_stats.h'
    stats_text=stats.read_text()
    stats_text=swap(stats_text,'    return __builtin_ia32_rdtsc();',
"""#if defined(__aarch64__)
    uint64_t ticks;
    __asm__ volatile("mrs %0, cntvct_el0" : "=r"(ticks));
    return ticks;
#else
    return __builtin_ia32_rdtsc();
#endif""",'SotC CPU cycle counter')
    stats.write_text(stats_text)
    tex=out/'shadps4/video_core/texture_cache/texture_cache.h'
    tex_text=tex.read_text()
    tex_text=swap(tex_text,'            __builtin_ia32_pause();',
"""#if defined(__aarch64__)
            __asm__ volatile("yield" ::: "memory");
#else
            __builtin_ia32_pause();
#endif""",'SotC texture-cache spin instruction')
    tex.write_text(tex_text)

    # Android AArch64 defines uint64_t as unsigned long, while desktop
    # x86-64's 64-bit literals can be unsigned long long. Make expressions
    # explicitly match the existing u64/VAddr contracts without narrowing.
    buffer=out/'shadps4/video_core/buffer_cache/buffer_cache.cpp'
    buffer_text=buffer.read_text()
    buffer_text=swap(buffer_text,
         'return std::bit_floor(kib == 1 ? u64{64} : std::clamp<u64>(kib, 4, 512)) * 1_KB;',
         'return static_cast<u64>(std::bit_floor(kib == 1 ? u64{64} : std::clamp<u64>(kib, 4, 512)) * 1_KB);',
         'SotC narrow readback lambda')
    buffer_text=swap(buffer_text,
         'return (v ? std::strtoull(v, nullptr, 10) : 4096ULL) * 1_KB;',
         'return static_cast<u64>((v ? std::strtoull(v, nullptr, 10) : 4096ULL) * 1_KB);',
         'SotC streaming readback lambda')
    buffer_text=swap(buffer_text,
         'std::min(Common::AlignDown(page, 4_KB) + 4_KB, range_end)',
         'std::min<VAddr>(Common::AlignDown(page, 4_KB) + 4_KB, range_end)',
         'SotC page range min')
    buffer.write_text(buffer_text)

    # The original POSIX signal frame adapter handles x86_64 only.
    # On Bionic, the signal frame holds ARM64 *host* registers. Guest x86
    # execution state remains in FEX and must never be fabricated from x0-x30.
    signal=out/'shadps4/common/signal_context.cpp'
    signal_text=signal.read_text()
    signal_text=swap(signal_text,'#include "common/arch.h"',
        '''#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include "common/arch.h"''','ARM64 signal helpers')
    signal_text=swap(signal_text,
        '    return (void*)((ucontext_t*)ctx)->uc_mcontext.gregs[REG_RIP];',
        '''    return (void*)((ucontext_t*)ctx)->uc_mcontext.gregs[REG_RIP];''',
        'desktop RIP branch validation')
    signal_text=swap(signal_text,
        '''    return (void*)((ucontext_t*)ctx)->uc_mcontext.gregs[REG_RIP];
#else
#error "Unsupported architecture"
#endif''',
        '''    return (void*)((ucontext_t*)ctx)->uc_mcontext.gregs[REG_RIP];
#elif defined(ARCH_ARM64) && defined(__linux__)
    return (void*)((ucontext_t*)ctx)->uc_mcontext.pc;
#else
#error "Unsupported architecture"
#endif''','AArch64 PC in signal context')
    signal_text=swap(signal_text,
        '''    gregs[REG_RIP] += length;
#else
#error "Unsupported architecture"
#endif''',
        '''    gregs[REG_RIP] += length;
#elif defined(ARCH_ARM64) && defined(__linux__)
    // Guest register index is x86 encoding. An ARM64 Linux signal frame
    // contains FEX's translated host registers, not those guest registers.
    (void)ctx; (void)gpr_index; (void)length;
    std::abort(); // Fail explicitly rather than silently corrupting the guest.
#else
#error "Unsupported architecture"
#endif''','AArch64 unsupported x86 guest register mutation')
    signal_text=swap(signal_text,
        'bool IsWriteError(void* ctx) {',
        '''#if defined(ARCH_ARM64) && defined(__linux__)
static std::uint64_t SotcArm64FaultEsr(void* ctx) {
    struct Record { std::uint32_t magic, size; std::uint64_t esr; };
    constexpr std::uint32_t EsrMagic=0x45535201;
    const auto& mc=((ucontext_t*)ctx)->uc_mcontext;
    const auto* data=reinterpret_cast<const unsigned char*>(mc.__reserved);
    for(std::size_t off=0;off+sizeof(std::uint32_t)*2<=sizeof(mc.__reserved);) {
        Record r{};
        std::memcpy(&r,data+off,
                    std::min(sizeof(r),sizeof(mc.__reserved)-off));
        if(!r.magic || r.size<8 || r.size>sizeof(mc.__reserved)-off) break;
        if(r.magic==EsrMagic && r.size>=sizeof(r)) return r.esr;
        off+=r.size;
    }
    return 0;
}
#endif

bool IsWriteError(void* ctx) {''','Linux ARM64 ESR record')
    signal_text=swap(signal_text,
        '''    return ((ucontext_t*)ctx)->uc_mcontext.gregs[REG_ERR] & 0x2;
#else
#error "Unsupported architecture"
#endif''',
        '''    return ((ucontext_t*)ctx)->uc_mcontext.gregs[REG_ERR] & 0x2;
#elif defined(ARCH_ARM64) && defined(__linux__)
    return (SotcArm64FaultEsr(ctx) & 0x40) != 0;
#else
#error "Unsupported architecture"
#endif''','AArch64 write-fault ESR')
    signal.write_text(signal_text)
    raster=out/'shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp'
    raster_text=raster.read_text()
    raster_text=swap(raster_text,
        'return std::strtoull(v, nullptr, 10);',
        'return static_cast<u64>(std::strtoull(v, nullptr, 10));',
        'SotC FLUSH_US ARM64 lambda return type')
    raster.write_text(raster_text)

    # Cache packing was implemented using Win32 _wfopen and wchar paths.
    # Android's std::filesystem::path is UTF-8 bytes: use the real POSIX
    # fopen rather than a nonexistent Windows wide-file API.
    cache=out/'shadps4/video_core/cache_storage.cpp'
    cache_code=cache.read_text()
    cache_code=swap(cache_code,
        'std::FILE* f = _wfopen(path.c_str(), L"rb");',
        '''#ifdef _WIN32
    std::FILE* f = _wfopen(path.c_str(), L"rb");
#else
    std::FILE* f = std::fopen(path.c_str(), "rb");
#endif''','SotC cache pack read')
    cache_code=swap(cache_code,'tmp += L".tmp";','tmp += ".tmp";',
                    'SotC cache pack temporary name')
    cache_code=swap(cache_code,
        'std::FILE* f = _wfopen(tmp.c_str(), L"wb");',
        '''#ifdef _WIN32
    std::FILE* f = _wfopen(tmp.c_str(), L"wb");
#else
    std::FILE* f = std::fopen(tmp.c_str(), "wb");
#endif''','SotC cache pack write')
    cache.write_text(cache_code)
    pipeline=out/'shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp'
    pipeline_text=pipeline.read_text()
    pipeline_text=swap(pipeline_text,
         'if (std::FILE* f = _wfopen(path.c_str(), L"rb")) {',
         '''#ifdef _WIN32
        std::FILE* cache_file = _wfopen(path.c_str(), L"rb");
#else
        std::FILE* cache_file = std::fopen(path.c_str(), "rb");
#endif
        if (std::FILE* f = cache_file) {''',
         'SotC driver cache load')
    pipeline_text=swap(pipeline_text, 'tmp += L".tmp";', 'tmp += ".tmp";',
                       'SotC driver cache temporary path')
    pipeline_text=swap(pipeline_text,
         'std::FILE* f = _wfopen(tmp.c_str(), L"wb");',
         '''#ifdef _WIN32
    std::FILE* f = _wfopen(tmp.c_str(), L"wb");
#else
    std::FILE* f = std::fopen(tmp.c_str(), "wb");
#endif''',
         'SotC driver cache store')
    pipeline.write_text(pipeline_text)

    # The Windows high-resolution waitable timer in the optional FSR3
    # frame generator is not available on Bionic. Preserve the rest of the
    # real SotC FSR3 GPU path and use a monotonic host clock for pacing.
    fsr_fg=out/'shadps4/video_core/renderer_vulkan/vk_fsrfg.cpp'
    fg_text=fsr_fg.read_text()
    fg_text=swap(fg_text,'#include <windows.h>',
        '#ifdef _WIN32\n#include <windows.h>\n#else\n#include <thread>\n#endif',
        'FSR3 Windows platform header')
    fg_text=swap(fg_text,'void SleepUntil(Clock::time_point due) {\n    static HANDLE timer =',
        '''void SleepUntil(Clock::time_point due) {
#ifndef _WIN32
    using namespace std::chrono_literals;
    for (;;) {
        const auto remaining=due-Clock::now();
        if (remaining<=0ns) return;
        if (remaining>1500us)
            std::this_thread::sleep_for(remaining-1000us);
        else
            std::this_thread::yield();
    }
#else
    static HANDLE timer =''',
        'SotC FSR3 native frame pacing')
    fg_text=swap(fg_text,
        '        YieldProcessor();\n    }\n}\n\n} // namespace',
        '        YieldProcessor();\n    }\n#endif\n}\n\n} // namespace',
        'SotC FSR3 Win32 timer closure')
    fsr_fg.write_text(fg_text)
    page=out/'shadps4/video_core/page_manager.cpp'
    page_code=page.read_text()
    page_code=swap(page_code,'char where[MAX_PATH] = "?";',
                        'char where[512] = "?";','SotC fault diagnostic path')
    page.write_text(page_code)

    # More upstream performance probes used Intel-only intrinsics. Replace
    # their underlying operations on AArch64 without disabling the waits.
    for relative in (
        'shadps4/video_core/renderer_vulkan/vk_scheduler.cpp',
        'shadps4/video_core/renderer_vulkan/vk_semaphore.cpp',
    ):
        target=out/relative
        original=target.read_text()
        original=swap(original,'#include <immintrin.h>',
"""#if defined(__aarch64__)
#define SOTC_CPU_RELAX() __asm__ volatile("yield" ::: "memory")
#else
#include <immintrin.h>
#define SOTC_CPU_RELAX() _mm_pause()
#endif""",'native spin macro '+relative)
        if '_mm_pause();' not in original:
            raise ValueError('Expected Intel spin instruction in '+relative)
        original=original.replace('_mm_pause();','SOTC_CPU_RELAX();')
        target.write_text(original)
    write_log=out/'shim/bbport_write_log.cpp'
    log_source=write_log.read_text()
    log_source=swap(log_source,'#include <x86intrin.h>',
"""#if defined(__aarch64__)
#include <chrono>
static std::uint64_t SotcHostCycles() {
    // Existing log prints time differences at 3GHz. A 3x monotonic-ns clock
    // retains its 10-second rollup and diagnostic seconds on Android.
    const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    return static_cast<std::uint64_t>(ns) * 3;
}
#else
#include <x86intrin.h>
static std::uint64_t SotcHostCycles() { return __rdtsc(); }
#endif""",'SotC write log host counter')
    log_source=log_source.replace('__rdtsc()','SotcHostCycles()')
    # Restore the x86 fallback inside the new helper (avoid recursion).
    log_source=swap(log_source,'static std::uint64_t SotcHostCycles() { return SotcHostCycles(); }',
                    'static std::uint64_t SotcHostCycles() { return __rdtsc(); }',
                    'write log fallback')
    # A Linux ARM64 signal frame stores host x0..x30, not the guest's
    # x86 RAX/RBX. The desktop debug routine would interpret those as guest
    # pointers and dereference arbitrary memory in a signal handler. Keep
    # the write ring active but safely report that guest register dumps need
    # the separate FEX guest-context reader.
    log_source=swap(log_source,
        'extern "C" void bbgpu_dump_guest_writes(void* ucontext) {',
        '''#if defined(__aarch64__)
extern "C" void bbgpu_dump_guest_writes(void* ucontext) {
    (void)ucontext;
    if (BbWriteLog::Mode())
        std::fprintf(stderr, "SotC: ARM64 signal registers are host-side; guest register dump unavailable\\n");
}
#else
extern "C" void bbgpu_dump_guest_writes(void* ucontext) {''',
        'safe ARM64 host signal diagnostic')
    log_source+='\n#endif // __aarch64__ debug dump\n'
    write_log.write_text(log_source)

    # The original in-game menu expects desktop SDL events. On Android the
    # overlay remains available as an ImGui Vulkan compositor; input will be
    # forwarded by the Android controller/IME bridge, not SDL.
    overlay=out/'shim/bbport_overlay.cpp'
    pane=overlay.read_text()
    pane=swap(pane,'#include <SDL3/SDL.h>',
              '#ifndef __ANDROID__\n#include <SDL3/SDL.h>\n#endif','overlay SDL header')
    pane=swap(pane,'ImGuiKey KeyFromSdl(SDL_Keycode key) {',
              '#ifndef __ANDROID__\nImGuiKey KeyFromSdl(SDL_Keycode key) {',
              'overlay SDL key mapping')
    pane=swap(pane,'// sotc: a short message at the top of the screen',
              '#endif // !__ANDROID__ (SDL key mapping)\n// sotc: a short message at the top of the screen',
              'overlay SDL gamepad mapping')
    pane=swap(pane,'float PixelDensity(SDL_WindowID id) {',
              '#ifndef __ANDROID__\nfloat PixelDensity(SDL_WindowID id) {',
              'overlay pixel density')
    pane=swap(pane,'// Marks the settings dirty when a widget changed them.',
              '#endif // !__ANDROID__ (SDL display)\n// Marks the settings dirty when a widget changed them.',
              'overlay display block')
    pane=swap(pane,'void UpdateTextInput(SDL_Window* window) {',
              '#ifdef __ANDROID__\nvoid UpdateTextInput(SDL_Window*) {}\nbool HandleEvent(const SDL_Event&) { return false; }\n#else\nvoid UpdateTextInput(SDL_Window* window) {',
              'overlay event stub')
    pane=swap(pane,'bool LoadingShown() {',
              '#endif // !__ANDROID__ (SDL window events)\nbool LoadingShown() {',
              'overlay event block')
    # UI translations are runtime strings, not printf-style format literals.
    # Android NDK enables -Wformat-security; no-argument ImGui printf calls
    # need a fixed "%s" format so translations cannot be interpreted as code.
    for portuguese,english in (
        ('Geração de quadros: desligada','Frame generation: off'),
        ('DLSS-G: aguardando (sem cena 3D)','DLSS-G: waiting (no 3D scene)'),
        ('FSR 3: aguardando (sem cena 3D)','FSR 3: waiting (no 3D scene)'),
    ):
        call='ImGui::TextColored(grey, SotcUi::T("'+portuguese+'", "'+english+'"))'
        pane=swap(pane,call,
                  'ImGui::TextColored(grey, "%s", SotcUi::T("'+portuguese+'", "'+english+'"))',
                  'safe translated UI text '+english)
    # SotC Android renders directly to the AHB presenter; the desktop
    # Dear ImGui helper window and swapchain are never created. ImGui's
    # dynamic-loader table nevertheless requires desktop surface functions.
    # Mark only those unused entries optional. All actually used functions
    # remain mandatory and are checked before ImGui_ImplVulkan_Init.
    imgui_backend=out/'third_party/imgui/backends/imgui_impl_vulkan.cpp'
    imguivk=imgui_backend.read_text()
    imguivk=swap(imguivk, '#include <stdio.h>',
        '#include <stdio.h>\n#ifdef __ANDROID__\n#include <cstring>\n#endif',
        'SotC Android ImGui platform function include')
    imguivk=swap(imguivk,
        'bool    ImGui_ImplVulkan_LoadFunctions(',
        '''#ifdef IMGUI_IMPL_VULKAN_USE_LOADER
#ifdef __ANDROID__
// ImGui's desktop window helpers are never called on the AHB headless path.
// Do not require their VkSurfaceKHR/VkSwapchainKHR exports to load the overlay.
static bool SotcUnusedDesktopVkFunction(const char* name) {
    return std::strcmp(name, "vkCreateSwapchainKHR") == 0 ||
           std::strcmp(name, "vkDestroySurfaceKHR") == 0 ||
           std::strcmp(name, "vkDestroySwapchainKHR") == 0 ||
           std::strcmp(name, "vkGetPhysicalDeviceSurfaceCapabilitiesKHR") == 0 ||
           std::strcmp(name, "vkGetPhysicalDeviceSurfaceFormatsKHR") == 0 ||
           std::strcmp(name, "vkGetPhysicalDeviceSurfacePresentModesKHR") == 0 ||
           std::strcmp(name, "vkGetSwapchainImagesKHR") == 0;
}
#else
static bool SotcUnusedDesktopVkFunction(const char*) { return false; }
#endif
#endif

bool    ImGui_ImplVulkan_LoadFunctions(''',
        'file-scope SotC Android optional swapchain function guard')
    imguivk=swap(imguivk,
        r'''    if (func == nullptr)   \
        return false;''',
        r'''    if (func == nullptr && !SotcUnusedDesktopVkFunction(#func)) { \
        ::fprintf(stderr, "SotC ImGui: required Vulkan entry %s is unavailable\n", #func); \
        return false; \
    }''',
        'fail safely when ImGui Vulkan loader misses required functions')
    imgui_backend.write_text(imguivk)

    pane=swap(pane,
        '''    ImGui_ImplVulkan_LoadFunctions(
        instance.ApiVersion(),
        [](const char* name, void* user) {
            return VULKAN_HPP_DEFAULT_DISPATCHER.vkGetInstanceProcAddr(
                *static_cast<const vk::Instance*>(user), name);
        },
        const_cast<vk::Instance*>(&vk_instance));''',
        '''    // Resolve device commands through vkGetDeviceProcAddr first. The
    // direct Turnip HAL path does not guarantee device commands through
    // vkGetInstanceProcAddr, and the fallback must not call NULL PFNs.
    struct SotcVulkanHandles { vk::Instance instance; vk::Device device; };
    SotcVulkanHandles handles{vk_instance, instance.GetDevice()};
    const bool functions_loaded=ImGui_ImplVulkan_LoadFunctions(
        instance.ApiVersion(),
        [](const char* name, void* user) -> PFN_vkVoidFunction {
            const auto& h=*static_cast<SotcVulkanHandles*>(user);
            PFN_vkVoidFunction fn=nullptr;
            if (VULKAN_HPP_DEFAULT_DISPATCHER.vkGetDeviceProcAddr)
                fn=VULKAN_HPP_DEFAULT_DISPATCHER.vkGetDeviceProcAddr(h.device,name);
            if (!fn && VULKAN_HPP_DEFAULT_DISPATCHER.vkGetInstanceProcAddr)
                fn=VULKAN_HPP_DEFAULT_DISPATCHER.vkGetInstanceProcAddr(h.instance,name);
            return fn;
        },
        &handles);
    if (!functions_loaded) {
        std::fprintf(stderr,
            "SotC Android: disabled Vulkan ImGui overlay (missing required entry); game renderer remains active\\n");
        ImGui::DestroyContext();
        s_instance=nullptr;
        return;
    }''',
        'SotC Vulkan Android ImGui required-function guard and device proc loader')
    overlay.write_text(pane)

    # SotC's original SRT walker only implements x86 Xbyak. Android needs
    # the validated portable ARM64 pass plus its cache/ABI adaptations.
    from stage_srt_arm64 import patch_sotc_arm64
    patch_sotc_arm64(root, out)
    from stage_adreno_wave32 import patch_adreno_wave32
    patch_adreno_wave32(out)
    # Recover dynamically indexed material/lighting textures on Android.
    # Staged SotC-only; vertex shader workaround remains explicitly excluded.
    from stage_fragment_tsharp import patch_fragment_tsharp
    patch_fragment_tsharp(out)
    # Reuse SotC's existing barycentric geometry-shader fallback on Adreno,
    # provided the selected Vulkan driver actually supports geometryShader.
    from stage_adreno_barycentric_gs import patch_adreno_barycentric_gs
    patch_adreno_barycentric_gs(out)
    # Android-only GS input/output uses the same standalone Position BuiltIn
    # as our preceding vertex shader; leave all interpolated varyings intact.
    from stage_adreno_gs_position import patch_adreno_gs_position
    patch_adreno_gs_position(out)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upstream',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[3]
    try:
        stage(a.upstream,a.out,root/'ports/sotc/android/window_android.cpp')
    except (OSError,ValueError) as e:
        p.exit(1,f'SotC renderer stage: {e}\n')
    print('Original SotC GPU staged with Android headless platform glue (compile pending)')
if __name__=='__main__':
    main()
