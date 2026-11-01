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
  "ARM64 real SRT implementation": 'order1886_arm64_srt.inc' in (gpu/"shadps4/shader_recompiler/ir/passes/flatten_extended_userdata_pass.cpp").read_text(),
  "ARM64 SRT interpreter": "void RunSrtProgram" in (gpu/"shadps4/shader_recompiler/ir/passes/order1886_arm64_srt.inc").read_text(),
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
