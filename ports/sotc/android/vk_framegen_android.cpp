// SotC Android: present actual game frames only until FSR frame-gen input
// extraction and the AHB presentation path have been validated.
// This does not disable the standalone spatial/temporal upscaler.
#include "video_core/renderer_vulkan/vk_framegen.h"
namespace Vulkan::FrameGen {
bool WantStreamline() { return false; }
bool HasNvidia() { return false; }
void SetAvailable(bool, bool) {}
Mode Current() { return Mode::Off; }
bool AskedAtStart() { return false; }
bool Available(Mode mode) { return mode == Mode::Off; }
Mode Cycle() { return Mode::Off; }
bool Set(Mode mode) { return mode == Mode::Off; }
const char* Name(Mode mode) {
    switch(mode) {
        case Mode::Off: return "off";
        case Mode::Dlss: return "DLSS-G unavailable on Android";
        case Mode::Fsr: return "FSR frame generation not yet ported";
    }
    return "off";
}
void TestTick() {}
} // namespace Vulkan::FrameGen
