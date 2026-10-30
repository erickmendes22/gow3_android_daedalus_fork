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
    set_target_properties(Vulkan::Vulkan PROPERTIES INTERFACE_LINK_LIBRARIES Vulkan::Headers)
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
    list(FILTER SHIM_SOURCES EXCLUDE REGEX "shim/window\\.cpp$")
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
endif()
"""
    c.write_text(t)
    shutil.copy2(android_window,out/'shim/window_android.cpp')
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
    overlay.write_text(pane)

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
