#!/usr/bin/env python3
"""Fail closed if the Android CPU boundary accidentally regresses to x86-only calls."""
import json
from pathlib import Path
import sys

tree=Path(sys.argv[1]) if len(sys.argv)>1 else Path("order-android")
p=(tree/"src/probe.c").read_text()
thread=(tree/"src/runtime_thread.c").read_text()
runtime=(tree/"src/runtime.c").read_text()
h=(tree/"src/runtime.h").read_text()
checks={
  "loader no x86-only hard error": "This prototype requires x86-64" not in p,
  "FEX loader init": "guest_cpu_init(runtime_low_map)" in p,
  "FEX imports": "guest_cpu_host_function((void*)resolved)" in p,
  "FEX main": "guest_cpu_call((uintptr_t)(image+entry),2,entry_args)" in p,
  "FEX module initializers": "guest_cpu_call((uintptr_t)(image+modules[m].init),3,init_args)" in p,
  "FEX signal handler": ("guest_cpu_signal_regs(context,&regs)" in p or "guest_cpu_signal_regs(context, &regs)" in p),
  "FEX TLS": "guest_cpu_set_gs(base)" in thread,
  "FEX thread start": "guest_cpu_call((uintptr_t)t->entry,1,&arg)" in thread,
  "FEX destructors": "guest_cpu_call((uintptr_t)handler.callback.plain,0,NULL)" in runtime,
  "ARM64 calling convention": "#define ABI\n#endif" in h,
  "Order PS4BOOT5 retained": "PS4BOOT5" in p,
  "Order trophy services retained": "runtime_trophy_configure" in p,
  "Order-specific renderer retained": "ps4gpu_init(&gpu)" in p,
}
gpu=tree/"gpu"
gpu_checks={
  "GPU timestamp profiler sampled and nonblocking":
      "sample_every=90_frames" in (gpu/"shadps4/video_core/renderer_vulkan/vk_gpu_profiler.cpp").read_text() and
      "vk::QueryResultFlagBits::eWait" not in (gpu/"shadps4/video_core/renderer_vulkan/vk_gpu_profiler.cpp").read_text(),
  "GPU stage labels at natural render pass boundaries":
      "shadow-depth-only" in (gpu/"shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text() and
      "MarkPass(pipeline, state);" not in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "Inline Vulkan tile clears preserve exact attachment state":
      "ORDER1886_GPU_INLINE_CLEAR reused=" in (gpu/"shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text() and
      "compared == new_state" in (gpu/"shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text(),
  "EVSM compute shadow restores HTILE before dispatch":
      "IsOrderEvsmShadowShader" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and
      "0x8ea0ef5bULL" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and
      "ORDER1886_EVSM_HTILE_FILL" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and
      "eDepthStencilAttachmentWrite" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "Shadow depth image source writes participate in Vulkan barrier scopes":
      "depth_source_scope" in (gpu/"shadps4/video_core/texture_cache/image.cpp").read_text() and
      "eLateFragmentTests" in (gpu/"shadps4/video_core/texture_cache/image.cpp").read_text(),
  "Task Kernel adaptive idle backoff remains isolated to Android":
      "ORDER1886_TASK_IDLE_BACKOFF" in (tree/"src/runtime_thread.c").read_text() and
      "strcmp(name,\"Task Kernel\")" in (tree/"src/runtime_thread.c").read_text(),
  "Compile-warning throttle preserves graphics and SRT fallbacks":
      "order1886_noncanonical_shaders" in (gpu/"shadps4/shader_recompiler/recompiler.cpp").read_text() and
      "unresolved_reports" in (gpu/"shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc").read_text(),
  "Sun cascade GPU AABB sync records and delivers completed snapshots":
      "KeepPageSynchronized" in (gpu/"shadps4/video_core/buffer_cache/buffer_cache.cpp").read_text() and
      "RecordSunCopies" in (gpu/"shadps4/video_core/buffer_cache/buffer_cache.cpp").read_text() and
      "DeliverSunCopies" in (gpu/"shadps4/video_core/buffer_cache/buffer_cache.cpp").read_text() and
      "0x7b1b18c9ULL" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "EVSM mutation reverted, HTILE moved to shadow depth clear":
      "mutable_cs.flattened_ud_buf" not in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and
      "ORDER1886_HTILE_DEPTH_CLEAR" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "VRS 2x2 capability header is present":
      (gpu/"shadps4/video_core/renderer_vulkan/order1886_vrs.h").is_file(),
  "VRS never requests 4x4":
      "fragment_size{vrs2x2 ? 2u : 1u" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and
      "4u : 1u" not in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "VRS never applies to alpha-discard or coverage-export fragment shaders":
      "fs->has_discard" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and
      "exports.coverage_to_mask_enable" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "VRS only coarsens depth-writing opaque half-resolution geometry":
      "halfres_scene" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and
      "regs.depth_control.depth_write_enable" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and
      "fs->has_discard" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "Adreno native driver cache replay stays disabled to avoid second-launch black screen":
      "ORDER1886_CACHE_REPLAY driver=disabled reason=single-msaa" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp").read_text(),
  "Adreno module warmup never replays serialized graphics pipeline state":
      "if (warm.shaders_only)" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp").read_text() and
      "warm.done.fetch_add(1, std::memory_order_relaxed);\n            continue;" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp").read_text(),
  "Adreno single sample background cache restores shader modules only":
      "warm.shaders_only" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp").read_text() and
      "Storage::BlobType::ShaderMeta" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp").read_text() and
      "ORDER1886_CACHE_REPLAY graphics=live shader_modules=" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp").read_text(),
  "VRS pipeline dynamic state enabled only after feature negotiation":
      "vk::DynamicState::eFragmentShadingRateKHR" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_graphics_pipeline.cpp").read_text() and
      "vrs_2x2_supported" in
      (gpu/"shadps4/video_core/renderer_vulkan/vk_instance.cpp").read_text(),
  "Actual attachment mask GPU timing":
      "MRT-2active" in (gpu/"shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text(),
  "Tile-friendly post-clear render pass reuse included":
      "ORDER1886_GPU_PASS_COALESCE merged=" in (gpu/"shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text(),
  "Crash regression fixed: speculative shadow-draw skip removed":
      "Order1886SkipShadowDepthWork" not in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and
      "ORDER1886_GPU_SHADOW_DEPTH_SKIP applied=" not in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "Mobile present barrier scope no longer ALL_COMMANDS":
      "No ALL_COMMANDS wait after the copy" in (gpu/"shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text(),
  "GPU profiler frame records when the temporal upscaler is off":
      "if (is_display_pass)" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "Patch 1 included in generated GPU shader resource code":
      "Order1886UnusedLightImage" in (gpu/"shadps4/shader_recompiler/resource.h").read_text() and
      "ORDER1886_LIGHT_GUARD" in (gpu/"shadps4/shader_recompiler/resource.h").read_text(),
  "Patch 2 included in generated GPU post-process code":
      "ORDER1886_PP_NOCLEAR" in (gpu/"shadps4/video_core/renderer_vulkan/host_passes/pp_pass.cpp").read_text() and
      "vk::AttachmentLoadOp::eDontCare" in (gpu/"shadps4/video_core/renderer_vulkan/host_passes/pp_pass.cpp").read_text(),
  "Patch 3 installed in generated Vulkan presenter":
      "ORDER1886_FAST_BGRA_BLIT" in (gpu/"shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text(),
  "Android SaveDataDialog controls wired": "PollAndroidChoiceControls" in (gpu/"shim/ps4_overlay.cpp").read_text(),
  "Android ImGui headless WSI optional": "Order1886OptionalHeadlessWsi" in (gpu/"third_party/imgui/backends/imgui_impl_vulkan.cpp").read_text(),
  "ARM64 real SRT implementation": 'order1886_arm64_srt.inc' in (gpu/"shadps4/shader_recompiler/ir/passes/flatten_extended_userdata_pass.cpp").read_text(),
  "ARM64 SRT cache serialization": "SrtWalkerCode(walker_func)" in (gpu/"shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp").read_text(),
  "Bachata V11 ARM64 duplicate ReadConst": "flat_multimap<IR::Value" in (gpu/"shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc").read_text() and "user_list.emplace(inst->Arg(1), inst);" in (gpu/"shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc").read_text(),
  "Bachata V6 The Order shader userdata": "0x9846aaffULL" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and "0x7F80000FU" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "Shader images not indiscriminately nulled": "IsBachataOrderNullImageShader" not in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "SRT guest read address trace": "TraceSrtSource(pointer, offset)" in (gpu/"shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc").read_text(),
  "Bachata exact GPU-written SRT pages": "ReadBackGpuWrittenSrtSources" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text() and "DownloadSrtSourcePage" in (gpu/"shadps4/video_core/buffer_cache/buffer_cache.cpp").read_text(),
  "Bachata bounded SRT refresh": "MaxPasses = 4" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "GPU-only SRT synchronization": "if (srt_sync) srt_sync(info)" in (gpu/"shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp").read_text(),
  "ReadConst GPU lowering invoked exactly once": (gpu/"shadps4/shader_recompiler/recompiler.cpp").read_text().count("LowerDynamicReadConstPass(program);") == 1,
  "ARM64 SRT interpreter": "void RunSrtProgram" in (gpu/"shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc").read_text(),
  "Upstream TranslateProgram callback retained": "const std::function<void()>& guest_reads_done" in (gpu/"shadps4/shader_recompiler/recompiler.cpp").read_text(),
  "Sampled image uniform guard retained": "SampledImageUniformGuardPass" in (gpu/"shadps4/shader_recompiler/recompiler.cpp").read_text(),
  "ReadConst GPU pass actually called": "LowerDynamicReadConstPass(program)" in (gpu/"shadps4/shader_recompiler/recompiler.cpp").read_text(),
  "CPU SRT filters GPU-varying offsets": "IsCpuSrtOffset" in (gpu/"shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc").read_text(),
  "ARM64 The Order ADDR64 ReadConst": "void LowerDynamicReadConstPass" in (gpu/"shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc").read_text(),
  "ARM64 SRT target not stubbed": "unimplemented for target architecture" not in (gpu/"shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc").read_text(),
  "ARM64 portable SRT cache": "SrtProgramCode" in (gpu/"shadps4/shader_recompiler/ir/passes/srt.h").read_text(),
  "Android GPU headless window": "WindowSystemType::Headless" in (gpu/"shim/window_android.cpp").read_text(),
  "Android AHardwareBuffer presentation": "AHARDWAREBUFFER" in (gpu/"shadps4/video_core/renderer_vulkan/vk_swapchain_ahb.cpp").read_text().upper(),
  "Android Vulkan external extensions": "VK_ANDROID_EXTERNAL_MEMORY_ANDROID_HARDWARE_BUFFER_EXTENSION_NAME" in (gpu/"shadps4/video_core/renderer_vulkan/vk_instance.cpp").read_text(),
  "Android Vulkan driver loader": "order1886_vk_get_instance_proc_addr" in (gpu/"shadps4/video_core/renderer_vulkan/vk_platform.cpp").read_text(),
  "Order renderer retained": "Ps4Overlay::OnPresented" in (gpu/"shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text(),
  "Desktop renderer preserved": "#ifndef __ANDROID__" in (gpu/"shadps4/video_core/renderer_vulkan/vk_swapchain.cpp").read_text(),
  "ARM64 portable CPU spin hint": "COMMON_CPU_RELAX()" in (gpu/"shim/ps4_threads.h").read_text(),
  "ARM64 portable Vulkan bind helpers": "Common::FencedRDTSC()" in (gpu/"shadps4/video_core/renderer_vulkan/vk_bind_helper.h").read_text(),
  "ARM64 portable Vulkan draw pipe": "COMMON_CPU_RELAX()" in (gpu/"shadps4/video_core/renderer_vulkan/vk_draw_pipe.h").read_text(),
  "ARM64 portable rasterizer timings": "Common::FencedRDTSC()" in (gpu/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text(),
  "AHB app protocol present": (tree/"tools/android/present/order1886_present_proto.h").is_file(),
  "Native Android frame receiver": (tree/"tools/android/bionic/present/order1886present.c").is_file(),
  "Android Java SurfaceView bridge": (tree/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/Order1886Present.java").is_file(),
  "Android pad native HLE ABI": "sizeof(PadData)==120" in (tree/"src/runtime_pad_bionic.c").read_text(),
  "Android PCM-to-FIFO native HLE": "ORDER1886_AUDIO_FIFO" in (tree/"src/runtime_audio_bionic.c").read_text(),
  "Java Android pad bridge": (tree/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/Order1886PadBridge.java").is_file(),
  "Java Android audio bridge": (tree/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/Order1886AudioBridge.java").is_file(),
  "Order ImGui menu preserved": "Ps4Overlay::Render" not in (gpu/"shim/ps4_overlay.cpp").read_text() or "namespace Ps4Overlay" in (gpu/"shim/ps4_overlay.cpp").read_text(),
}
checks.update(gpu_checks)
for key,ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {key}")
if not all(checks.values()):
    sys.exit(1)
meta=json.loads((tree/"ANDROID_PORT_MANIFEST.json").read_text())
assert meta["build_verified"] is False and not meta["android_gameplay_verified"]
print(f"Verified: {len(checks)} static CPU boundary conditions; not a gameplay test")
