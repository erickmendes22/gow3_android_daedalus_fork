// SPDX-License-Identifier: GPL-2.0-or-later
// SotC Android headless window. The Vulkan/AHB presenter owns the phone surface.
#ifdef __ANDROID__
#include "sdl_window.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>

namespace Frontend {
namespace {
std::atomic<bool> output_fullscreen{true};
bool screen_size(s32& w, s32& h) {
    const char *sw=std::getenv("SOTC_SCREEN_W");
    const char *sh=std::getenv("SOTC_SCREEN_H");
    if (!sw || !sh) return false;
    char *ew=nullptr,*eh=nullptr;
    long x=std::strtol(sw,&ew,10),y=std::strtol(sh,&eh,10);
    if (!ew || *ew || !eh || *eh || x<320 || y<180 || x>16384 || y>16384) return false;
    w=(s32)x; h=(s32)y;
    return true;
}
}
WindowSDL::WindowSDL(s32 w,s32 h,const char *name)
    : width{w}, height{h}, base_title{name ? name : "Shadow of the Colossus"} {
    if (w<320 || h<180) { w=1280; h=720; }
    screen_size(w,h);
    width.store(w,std::memory_order_relaxed);
    height.store(h,std::memory_order_relaxed);
    window_info.type=WindowSystemType::Headless;
    window_info.render_surface=nullptr;
    window_info.display_connection=nullptr;
    std::printf("SotC Android headless output %dx%d\n",w,h);
}
WindowSDL::~WindowSDL()=default;
void WindowSDL::SetFullscreen(bool enabled) {
    output_fullscreen.store(enabled,std::memory_order_relaxed);
}
bool WindowSDL::IsFullscreen() const {
    return output_fullscreen.load(std::memory_order_relaxed);
}
bool WindowSDL::PollEvents() { return is_open.load(std::memory_order_relaxed); }
void WindowSDL::BeginTextInput(const std::string&,const std::string&) {
    // Android launcher will supply IME events; never block rendering.
    std::lock_guard<std::mutex> lock(text_mutex);
    text_state=2;
    text_active=false;
    text_requested=false;
}
int WindowSDL::PollTextInput(std::string&) {
    std::lock_guard<std::mutex> lock(text_mutex);
    return 2;
}
void WindowSDL::UpdateTitleStats() {}
void WindowSDL::UpdateTextTitle() {}
} // namespace Frontend
#endif
