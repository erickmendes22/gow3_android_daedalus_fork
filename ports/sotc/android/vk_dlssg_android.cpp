// SotC Android: NVIDIA Streamline is Windows/DXGI specific.
// Preserve ABI and FSR upscaler path; DLSS super resolution/frame-gen and
// dependent camera/HUD capture are unavailable until a native port is made.
#include "video_core/renderer_vulkan/vk_dlssg.h"
#include <atomic>

// The PC 0.74 presenter and rasterizer require these exact API functions.
// Android cannot load the NVIDIA Streamline DLL, but these symbols must be
// defined in libbbgpu.so or Android's dlopen rejects the whole renderer.
// The HDR curve is an engine-side value, independent of NVIDIA's backend.
namespace Vulkan::Dlssg {
namespace {
std::atomic<float> s_hdr_curve{1.0f};
}
void SetHdr(bool) {}
void NoteHdrCurve(float k) { s_hdr_curve.store(k, std::memory_order_relaxed); }
float HdrCurve() { return s_hdr_curve.load(std::memory_order_relaxed); }
bool CameraLogOnly() { return false; }
void NoteCamera(const AmdGpu::Regs&, u32) {}
bool SuperResolutionUpscaling() { return false; }
PFN_vkGetInstanceProcAddr LoadInterposer() { return nullptr; }
void OnDeviceCreated(const Instance&) {}
bool Enabled() { return false; }
bool CapturingInputs() { return false; }
bool WantsImmediatePresent() { return false; }
void NoteDraw(const AmdGpu::Regs&, u32, VideoCore::ImageId, VideoCore::ImageId,
              VideoCore::TextureCache&, Runtime&, Scheduler&) {}
void PrepareInputs(u32, vk::CommandBuffer, VideoCore::TextureCache&,
                   Runtime&, u32, u32) {}
void NoteHudless(u32, vk::Image, vk::ImageView, vk::Format, u32, u32) {}
bool SuperResolution() { return false; }
bool SuperResolutionAvailable() { return false; }
bool CompareMode() { return false; }
const char* ModeName() { return "DLSS unavailable"; }
void ToggleSuperResolution() {}
void NoteVignette(const float[4]) {}
bool Vignette(float[4]) { return false; }
void NoteComposite(VideoCore::ImageId, VideoCore::ImageId, VideoCore::TextureCache&) {}
bool UiTarget(VAddr, u32, u32, u32&, u32&) { return false; }
void NoteUiShadow(vk::Image, u32, u32) {}
Upscaled Upscale(u32, Scheduler&, VideoCore::TextureCache&, Runtime&, u32, u32) { return {}; }
void FrameSubmitted(u32) {}
void NoInputs(u32) {}
void BeforePresent(u32, vk::Rect2D, vk::Extent2D) {}
void AfterPresent(u32) {}
void Suspend() {}
bool GetFrameInputs(u32, FrameInputs&) { return false; }
} // namespace Vulkan::Dlssg
