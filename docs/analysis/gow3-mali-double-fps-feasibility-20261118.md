# GoW III / Mali-G720 MC7 — 2× FPS feasibility and source audit (2026-11-18)

Status: **research branch, no APK, no claim of measured speedup**. Based on `perf/gow3-mali-bachata-gc-batch-20261112` (contains the 2026-11-13 barrier, Early-Z, MultiCopy, draw-bind and GC work). Any later build must use the intended release branch, after a tested promotion.

## Real baseline and acceptance threshold
- `docs/analysis/gow3-g720-20261113-three-log-attribution.md`: 11 compile-free windows, >2,000 draws/frame, average **5.2727 FPS** (2,567 draws/frame) at **960×540**, PanVK 26.3.1, Mali-G720 MC7.
- Reciprocal average: **189.656 ms/frame**. >2× requires **>10.5454 FPS**, **<94.828 ms/frame**, i.e. remove **>94.828 ms from the actual critical path**, not merely from overlapping wall-clock counters.
- Separate 1280×720 scene: 3.7–5.7 FPS at 2,536–3,047 draws/frame; do not combine its frame times with the 960×540 base.
- 82.1% CPU blocked on GPU-ticks does **not** imply 82.1% fragment-shader GPU time.

## Source-code findings: what is already there
1. GoW SPIR-V `gpu/shadps4/shader_recompiler/backend/spirv/emit_spirv.cpp::Traverse` **already** outputs structured `OpSelectionMerge` / `OpLoopMerge`: LASRecomp #562's 10→20 FPS fix is for its own preexisting pc-loop switch and cannot be counted as a GoW improvement.
2. `shader_recompiler/resource.h::PushData` is **128 bytes already**. The LASRecomp #563 fast constant-buffer promotion requires new stage metadata, read-only safety, stage-specific pipeline layout, per-draw reads and GPU-dirty/alias fallback; extending it to 256 without runtime `maxPushConstantsSize` check breaks other drivers. LASRecomp reports a 23–25→27–28 FPS *incremental* improvement after structured shaders, not 2× from push constants alone.
3. LASRecomp #564 (placed coherent-aware guest heap, write tracking) was tested on Linux Panthor+PanVK, **not stock Android kbase**; cannot assume `VK_EXT_map_memory_placed`/host cached memory semantics identical on the G720 or bypass guest GPU dirty aliases.
4. Existing GoW branch already has deferred fused descriptor/constant and vertex/index record, pipeline-bind and vertex-input caching, scene memory pools, PM4 blocked-yield backoff, GC batching, optional precise buffer barriers (`GOW3_MALI_LOCAL_BUFFER_BARRIERS`), optional sampled-stage barriers (`GOW3_MALI_SHADER_STAGE_BARRIERS`), Early-Z and opt-in compute MultiCopy. Driver build 122i already incorporates many Zen CSF/tiler/BC optimizations. Do **not** double count these.
5. 2026-11-13 local synthetic report: even eliminating all old MultiCopy region operations only gives ~2.16 ms/frame, raising 5.2727→5.3335 FPS (+1.15%); Early-Z remains unmeasured. 400 ms vkCreateImage/driver spikes, 642 ms synchronous GC download batches and shader rebuilds explain spikes, but not compile-free steady-frame 189 ms.
6. PanVK driver `wonderkast02/panvk-g720-kbase-csf` 0.1.0-beta.2 has GPU WAIT64/GS/TES support, and a Bachata v0.2.4 report on the G720 MC7 says 43.3 average FPS for a long, unpaired session; its **1% low was 1.5 FPS**. Another session on the same device/driver family averaged 27.4 with 8.2 1%-low. These are **not matched 960×540 heavy-scene A/B**, so cannot establish >2× for Daedalus or transfer the average to the 2,500+ draw scene.
7. MineGraph PanVK 26.3.0 panvk.7 (2026-11-16), tested G715, adds zero-copy Android present, mediump default and KRAID compiler updates; Daedalus' native AHB copy is usually ~0.3–0.5 ms/frame, so zero-copy is not a 95ms win. KRAID and mediump need same-G720 compiled shader statistics and visual correctness before integration.
8. JimVulkan Mesa 27 and Zen 122i are already represented in GoW device logs/package. Blindly exchanging them does not qualify as new optimization.

## Highest-impact new candidates (not implemented; rank reflects investigative priority)
A. **Mali constant-buffer hot-word promotion**: IR histogram for literal-index `ReadConstBuffer` loads and loop-weighted use counts, and optional stage-specific push-constant slots only when bound buffer data is provably stable/readable by host and there is sufficient `maxPushConstantsSize` capacity. No GPU-dirty aliased buffer, no dynamic indices, no unbounded readback; preserve original SPIR-V on rejected shaders. Cache key and profile signature must include the new lowering.
B. **Mali compiler register-pressure reduction**: compare shader driver executable statistics / spill counts for the dominant PS/VS/TES/GS against Zen 122i, Jim Mesa27 and MineGraph KRAID on the SAME shader. GPU shader code may be much slower than CPU Vulkan generation; do not assume GPU fractions from host waits.
C. **PanVK pre-raster tessellation/geometry and tiler**: isolate count and GPU time of GS/TES passes, driver GPU WAIT64 and tiler/fragment preloads. Upstream Zen already has GPU waits and renderpass optimizations; port only demonstrably missing behavior. Never skip semantic dependencies or occlusion.
D. **Precise barriers and texture lifetime**: branch already implements guarded buffer/image barrier narrowing and GC batch; measure non-overlapping GPU idle and preserve all alias/data hazards. Reject resizing VkImage in place, arbitrary image-key relaxations, unconditional Early-Z and speculative high worker count.
E. **Frame spikes (separate target)**: current Mali API call trace can distinguish `vkCreateImage`, `vkAllocateMemory`, image requirements and bind. Pool quota increases cannot fix `miss_incompatible`; driver-rebind allocation shape must be exact. Cache-schema invalidation shown only once, not every restart.

## Amdahl screen (mathematical scenarios, NOT predictions)
Use `T = 189.656 ms`. Suppose a fraction `f` of the **entire frame's actual critical path** (not 82% CPU wait) improves by factor `s`, with everything else unchanged:
`FPS_new = 5.2727 / (1 - f + f/s)`.
- f=60%, s=2: 7.532 FPS (1.43×).
- f=70%, s=3: 9.886 FPS (1.88×).
- f=75%, s=3: 10.545 FPS (exactly 2×, *not above*).
- f=80%, s=3: 11.298 FPS (2.14×), **only if 80% of total critical path is actually accelerated by 3×**.
- f=70%, s=4: 11.100 FPS (2.11×), requiring a 4× improvement on 70% of full frame time.
These scenarios are not independently supported by a measured GoW GPU profile; LASRecomp's measured 12→26 FPS combines a fix to an already-structured-in-GoW control-flow form with memory and constants. Multiplying independent marketing percentages would be invalid.

## No-build decision and exact proof gate
No independent combination with a defensible >2× **GoW G720 steady-FPS estimate** is verified. **Do not build a release APK or claim the user threshold met.**
Existing `vk_gpu_profiler.cpp` and `Rasterizer::MarkPass` already label 2D/3D render passes by size, formats and PS/VS hashes when `GOW3_GPU_PROFILE=1`. The dispositive missing evidence is a **same-save, same-resolution G720 pass GPU timestamp profile** plus stage compiler occupancy/spill statistics; from those, budget the real >94.8ms removal and select only candidates hitting the expensive stage. A test build for profiling is not an optimization release and is not authorized by this 2× APK gate.

## Sources
- https://github.com/peiikai/LASRecomp/issues/560
- https://github.com/peiikai/LASRecomp/pull/562
- https://github.com/peiikai/LASRecomp/pull/563
- https://github.com/peiikai/LASRecomp/pull/564
- https://github.com/wonderkast02/panvk-g720-kbase-csf/releases/tag/0.1.0-beta.2
- https://bachatas4.games/games/CUSA01715/
- https://github.com/MineGraph-bilibili/panvk-Android/releases/tag/Mesa.26.3.0-panvk.7
- https://github.com/JimVulkan/mali-panvk
- https://github.com/zenithblue-oss/panvk-kbase-android
- https://developer.arm.com/community/arm-community-blogs/b/mobile-graphics-and-gaming-blog/posts/vulkan-synchronization-how-pipeline-barriers-map-to-mali-gpu-hardware
