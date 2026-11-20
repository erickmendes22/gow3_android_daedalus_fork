# GoW III / G720 PanVK — freeze + heavy-scene remediation (2026-11-20)

**Branch:** `fix/gow3-panvk-freeze-heavy-fps-20261120` (based on `analysis/gow3-mali-double-fps-evidence-20261118`). Source fixes are **not** measured device gains. The tester APK is built and delivered after source/native compilation and signing checks; gameplay FPS/freezes are verified **on-device after installing it**, not required before building it.

## Observed G720 profile

Source log: `GodOfWar3-Logs-20261120-195724.zip`, `android-game.log`. Light frames at 58–60 FPS, heavy gameplay at 6.9–11.8 FPS, with ~1,112–2,632 draws/frame and at least one 766.5 ms frame. Late 6.45 s segment: 129,427 draws, 3,009 renderpass splits, 6,894 image barriers and 212,963 UBO bindings; no shader/pipeline compiles in that heavy segment. GPU-ticks blocking was ~62–76% of host time in heavy windows, **not a measurement of GPU fragment shader utilization**. AHB copy accounted for ~0.27 ms/sample, not the steady ~100–150 ms game-frame bottleneck. RGBA128 pool had 12 hits/308 misses (283 incompatible); allocation of 4096x168/208/232 RGBA128 images was recorded at 28–54 ms.

## Four source changes — and what they do not prove

1. **Prevent avoidable freezes, preserve GPU ownership:** optional repeated-frame presentation skips immediately if the async worker owns the frame or its fence has not signalled. The main PM4 producer no longer blocks on that optional repaint. The async readback worker polls the real GPU fence at 100 ms and emits infrequent `GOW3_MALI_PRESENT_FENCE_STALL` warnings. It only invalidates/copies/recycles a frame after confirmed completion. A **real driver GPU hang** is not recoverable by simply disregarding its fence: worker still waits for a signal rather than risking use-after-free. The repair targets preventable CPU-side stalls, not guaranteed driver recovery.
2. **Heavy-scene synchronization:** `vk_scheduler.cpp` waits for old GPU timeline ticks **before** holding the global submit mutex. This prevents cross-scheduler queue starvation while respecting `GOW3_VK_MAX_IN_FLIGHT`. Sampled-only image barriers may target the actual consuming shader stage, and read-only VS/FS UBO dependencies may do likewise. Storage images, attachment feedback writes, guest buffer writes and hazard tracking still use conservative guards. Rollbacks: `GOW3_MALI_SHADER_STAGE_BARRIERS=0`, `GOW3_MALI_PRECISE_UBO_BARRIERS=0`.
3. **Image allocation/pools:** the cross-description VMA rebind path now preserves one completed exact RGBA128 VkImage per shape, including existing ETC2 preservation. Guarded prewarm extends measured 4096x248 RGBA128 with 4096x168/208/232 shapes. No BC/ETC2 ↔ RGBA128 live image aliasing, stale image reuse, VMA budget bypass or relaxed VkImageCreateInfo matching. Rollback heavy prewarm: `GOW3_MALI_VMA_PREWARM_HEAVY=0`. The actual warmup may miss if guest Vulkan usage/flags differ from these known shapes; it is not evidence of FPS gain.
4. **Shader/UBO bottleneck mitigation:** shader compilation, key and descriptor layouts already implement `GOW3_UBO=2` and SPIR-V Early-Z, so this branch does not reimplement them or invalidate the shader cache. Instead it limits read-only UBO dependency stages to VS/FS, preserving all writes and fallbacks. Heavy-scene GPU shader/tiler **execution time cannot be quantified** from host `GPU ticks` alone; further simplification of shaders or skipping barriers without per-pass GPU timestamps would be speculative and risky.

## Code and static tests

- `gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp`
- `gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp`
- `gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp` and `.h`
- `gpu/shadps4/video_core/texture_cache/image.cpp`
- `tools/android/bionic/run-bionic.sh`
- `tests/test_mali_freeze_heavy_scene_regression.py`, plus updated async-readback and VMA tests.

## Device verification after native compilation

Use the same saved position and same resolution (960×540) with the same PanVK driver and warmed shader cache. Check median/p95/p99 frame times, freeze reproduction and `GOW3_MALI_PRESENT_FENCE_STALL`; record image-pool hits/misses, slow image allocations and the shader/barrier counters. Compare flags individually on that save with performance logging disabled during the decisive A/B, retaining source and driver configuration. `GOW3_GPU_PROFILE=1` can be used for a separate *attribution* run, **not** a directly comparable FPS run because profiling breaks passes. No measured heavy-scene speedup is claimed until this A/B.

**Tester packaging:** The `gow3-mali-double-fps-test-apk.yml` workflow on this branch compiles native ARM64 code, creates the separately installable, consistently signed Mali test APK and uploads it as an artifact. CI checks compile/package integrity only and MUST NOT block the tester APK on an unmeasurable >2× FPS threshold or a claim of no device freezes. A stable public release can be evaluated after user-side gameplay and visual tests. The native-only workflow remains available separately.
