# Bachata S4 RELEASE ↔ Daedalus 2.1.8: Mali/PanVK source comparison

Scope: **Bachata S4 RELEASE**, not Bachata Plus. No test APK is required for this source audit.

## Provenance and limit

- RELEASE v0.2.5 publishes the following relevant fixes: PanVK V3 3.2.0,
  God of War III BCn-to-ETC2 transcode, tiler-heap recycling, RectList/QuadList
  shader corrections, and depth/stencil fixes.
  https://github.com/JICA98/Bachata-S4/releases/tag/v0.2.5
- The release repository points its emulator core to
  https://github.com/zenithblue-oss/shadps4-arm64 .
- The RELEASE v0.2.5 notes refer to source revision `8eb03d9e9`, but that
  specific tree was not available through the public source repositories during
  this audit. **Do not claim parity with or a verbatim port of that revision.**
- The audit below compares source files currently visible in the Bachata
  public core `main` with this Daedalus fork.

## Verified code comparison

| Component | Bachata public core | Daedalus before this change | Action |
|---|---|---|---|
| Vulkan push descriptors | `src/video_core/texture_cache/tile_manager.cpp`: chooses push descriptors conditionally and binds ordinary descriptor sets via `DescriptorHeap` otherwise | `gpu/shadps4/video_core/texture_cache/tile_manager.cpp`: unconditionally created push-descriptor layouts and called `pushDescriptorSetKHR` | **PORTED** ordinary-set fallback, with command-recording-thread-safe captured handles |
| Descriptor fallback for graphics pipeline | `vk_instance.cpp` and pipeline cache support unavailable extension | `vk_instance.cpp` already checks optional `VK_KHR_push_descriptor`; `vk_pipeline_cache.cpp` already uses `DescriptorHeap` | ALREADY PRESENT; leave untouched |
| RectList / QuadList auxiliary shaders | `emit_spirv_quad_rect.cpp` | Same 339-line implementation apart from three declarations naming the fragment runtime type | ALREADY EQUIVALENT; no transplant |
| Mali detile scratch allocator | Public Bachata uses opt-in ring `BACHATA_MALI_GPU_OPT` | Daedalus already has a reusable, GPU-tick-aware `StagingBufferPool`; mechanisms differ | NEEDS hardware comparison, not blindly copy two allocation models |
| BCn texture transcode to ETC2 | Announced in RELEASE v0.2.5 | Daedalus packages PanVK v3.2 and optional v26.3.1 with BCn support, but the emulator itself does **not** implement verified equivalent transcoding | **NOT PORTED**; source of RELEASE v0.2.5 conversion not available. Must inspect the actual release binary/source rather than assert equivalence |
| PanVK GPU tiler heap recycling | Announced in RELEASE v0.2.5 driver | Controlled by separately packaged PanVK driver, not `TileManager` in emulator | **UNVERIFIED** at binary level; don't confuse driver-internal tiler heap with emulator scratch allocation |
| Depth/stencil, image/view format compatibility | RELEASE notes list more fixes without accessible per-change source | Daedalus has physical-format fallback and RobustImage checks, but black scene persists | **UNRESOLVED**; don't represent current fixes as sufficient |

## Implemented now

- `tile_manager.h`: lifetime-safe `DescriptorHeap`, fallback descriptor pool sizes,
  and `uses_push_descriptors` capability state.
- `tile_manager.cpp`: choose push-descriptor layout only when the device
  advertises at least three push descriptors; otherwise allocate/update
  ordinary sets and bind them in the existing asynchronous recording lambda.
- No changes to Adreno's supported push-descriptor path.
- No automatic render-pass captures or driver substitution.

## Next release gate

Keep the testing distribution on hold until one **combined** build contains
all verified source-port fixes; native compilation and one Mali device test
must still validate runtime behavior. An APK build is not proof of graphics
correctness and no CI build was requested for this particular comparison.
