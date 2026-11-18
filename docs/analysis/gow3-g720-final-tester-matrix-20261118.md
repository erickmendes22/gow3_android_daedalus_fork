# GoW III Mali G720: consolidated fixes, 2x-estimate decision and tester A/B

Date: 2026-11-18. Source: analysis/gow3-mali-double-fps-evidence-20261118.
**This is a mathematical feasibility screen, NOT a Mali benchmark.**

## Matched baseline / acceptance
- Same previously captured G720 MC7 PanVK 960x540 heavy save, ~2,567 draws/frame: 5.2727 FPS, 189.656 ms/frame in warm no-compile windows.
- 2x means >=10.5454 FPS or <=94.828 ms/frame. **More** than 2x requires faster than those boundaries.
- Do not compare different 1280x720 scenes (3.7-5.7 FPS) or a 480p Bachata session to the heavy 960x540 scene. Ticks blocked represent CPU wait for GPU, not GPU stage fractions.

## Confirmed source defects fixed on research branch
1. **PanVK AFBC**: the generic color-image creation always requested Vulkan STORAGE usage, preventing PanVK AFBC for color render targets. On PanVK Android G720, eligible 2D <=32bpp single-sample pure color images omit STORAGE and preserve compression eligibility. ImageStore always uses/gets a STORAGE-capable image; if needed, `ExpandImage` transfers the prior image's GPU content. Rollback `GOW3_MALI_AFBC_COLOR_RT=0`. Counters: `afbc_candidates`, `afbc_storage_upgrades`. Candidate count is **not** actual compression confirmation; driver debug flags may disable AFBC.
2. **UniformBuffer shader constants**: U32/F32 read-only VS/FS guest buffers up to 16 KiB become uniform descriptors, default `GOW3_UBO=2`. Vulkan 1.2 `uniformBufferStandardLayout` MUST be enabled and buffer alignment <=256 to fit existing 8-bit guest push offset; otherwise automatic SSBO fallback. Shader SPIR-V and all bindings use the immutable persisted pipeline descriptor masks, including background warmup. Cached shader metadata and layout keys invalidated correctly. Constant ring pads and flushes declared UBO length. Rollback `GOW3_UBO=0`. Check `GOW3_UBO_DEVICE ... active=1` in the log; `requested=2` alone is NOT enough.
3. **Driver allocation duplication**: optional rebind previously called vkCreateImage just to find that no retired allocation could be rebound, then did normal vmaCreateImage. Added bounded, device-generation-invalidated exact-description memory-requirements memo and fast rejection of demonstrably incompatible retired blocks. All candidate Vulkan size/alignment/type/dedicated guards, completed-GPU rules and VMA fallback preserved. Counters: `image_rebind_probe`, `rebind_fast_reject`, `rebind_incompatible`, `rebind_success`. Rollback `GOW3_MALI_REBIND_RETIRED_MEMORY=0`.
4. **Vulkan barriers**: Mali-only image/buffer split already enabled; bounded exact VkBuffer range barriers (max 8, fallback to global on overflow/invalid/submit) enabled in tester profile, rollback `GOW3_MALI_LOCAL_BUFFER_BARRIERS=0`. Does not remove any required dependency, only narrows its scope. Counter `pass_splits`, `local_buffer_barriers`, `global_barriers`, `image_barriers`.
5. **Why so many draws?** new topology counts `rect`, `quad`, `native_tess`, `geometry` distinguish auxiliary TCS/TES and native stages. The expensive tessellation case is not patched speculatively without seeing whether it occurs in the slow scene. Avoid bypassing semantic pipeline stages.

## Estimated FPS scenarios, conditional
The improvements are NOT independent proven FPS multipliers. UBO measured **22.2→29.5 FPS** (~1.33x) in an *Adreno* GoW3 scene (PR #9), **not PanVK**. Khronos measured ~33% **bandwidth reduction** with AFBC in a *different Vulkan application*, **not GoW3 FPS**. A conservative and a high-end estimate therefore require *explicit hypothetical non-overlapping frame-time buckets*.

Let T0=189.656ms/frame. Assign each full-frame latency bucket to a distinct cost so no double counting; savings are upper-bound *conditional*, not measured:

| Scenario | AFBC-related GPU framebuffer memory | shader constant access | barriers/tiler | other | Result |
|---|---|---|---|---|---|
| Central hypothetical | 70ms x 30% saved=21ms | 50ms x 30% saved=15ms | 35ms x 25% saved=8.75ms | untouched 34.656ms | 144.906ms = 6.90 FPS (1.31x) |
| Aggressive plausible upper | 90ms x 50%=45ms | 55ms x 45%=24.75ms | 30ms x 65%=19.5ms | untouched 14.656ms | 100.406ms = 9.96 FPS (1.90x) |
| >2x *test gate* | 90ms x 55%=49.5ms | 55ms x 45%=24.75ms | 30ms x 75%=22.5ms | untouched 14.656ms | 92.906ms = 10.76 FPS (2.04x) |

**Crucial:** the last row is the *required best-case performance distribution*, not an expectation. We DO NOT know those three category lengths or savings yet. Without a GPU pass/driver counter capture, there is no defensible empirical evidence that >2x is likely. The only way to measure device FPS is a tester APK; a safety-verified, clearly labeled experimental APK can now be used for the A/B.

## Test instructions (same heavy save and driver; 960x540)
- Warm up to the same scene. Use the same PanVK Mesa 26.3.1 and clock/cooler, ideally 30–60s after shader preflight. Capture `Frame stats`, `MALI_CAUSAL_COUNTS`, `GOW3_UBO_DEVICE`, image-pool diagnostics and `GOW3_MALI_SLOW_IMAGE_ALLOC`. First launch after new schema rebuilds shader metadata; compare the following warm-cache launch.
- Run normal defaults first: `GOW3_UBO=2`, `GOW3_MALI_AFBC_COLOR_RT=1`, `GOW3_MALI_LOCAL_BUFFER_BARRIERS=1`. Verify active=1 in `GOW3_UBO_DEVICE`, count of AFBC candidates, and ideally zero or few storage upgrades.
- For regression isolation change **one** variable at a time: UBO=0, AFBC=0, local_buffer_barriers=0, rebind=0. Compare same-save median/p95 frame time and graphics correctness. UBO toggle changes cache schema; allow warmup.
- If `rect/quad` and `native_tess/geometry` are large, prioritize tessellation emulation analysis before tuning texture caches. If `pass_splits` is enormous, inspect GPU timestamps in a separate `GOW3_GPU_PROFILE=1` capture (that profiling itself breaks passes; **do not** treat its FPS as baseline).
- Check 1.02 normal gameplay: lighting/materials, text, cutscenes/video, saves, controller, transitions, sleep/resume; verify no device loss, textures missing, or wrongly aligned constants.

Sources:
- https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/47e8d5c1846b219ea6d30a5ab4b6c608c8bcd1e7/src/panfrost/vulkan/panvk_image.c
- https://docs.vulkan.org/samples/latest/samples/performance/afbc/README.html
- https://github.com/erickmendes22/gow3_android_daedalus_fork/pull/9
