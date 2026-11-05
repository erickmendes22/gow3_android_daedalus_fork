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
- **V3.2 PanVK provenance established from the actual Daedalus APK**:
  `PanVK-android-v3.2-universal-2a9358a.zip` declares source revision
  `2a9358a000fd691dac36d04c170fa3bd4101ff06` from
  `https://github.com/JICA98/panvk-kbase-android`, branch
  `bachata/v3-upstream-beta13`. Its `patches/bachata-v3/0007-...patch`
  implements kbase GPU-tiler heap recycling. The bundled V3.2 `.so` includes
  the `PANVK_KBASE_SKIP_HEAP_OPS` control.
- The existing alternate driver `Mesa-PanVK-Android-v26.3.1-795ca7ff.adpkg.zip`
  is already in the APK. Its binary includes `etc2_encode_bc1_pal`,
  `etc2_encode_rgb`, `PANVK_BC_RAW`, and `PANVK_BC_AFRC`. It is selected
  automatically on supported Mali-G615 when available, otherwise V3.2 remains
  selectable. **A symbol alone does not establish that transcoding was used
  during a particular game run.**

## Verified code comparison

| Component | Bachata public core | Daedalus before this change | Action |
|---|---|---|---|
| Vulkan push descriptors | `src/video_core/texture_cache/tile_manager.cpp`: chooses push descriptors conditionally and binds ordinary descriptor sets via `DescriptorHeap` otherwise | `gpu/shadps4/video_core/texture_cache/tile_manager.cpp`: unconditionally created push-descriptor layouts and called `pushDescriptorSetKHR` | **PORTED** ordinary-set fallback, with command-recording-thread-safe captured handles |
| Descriptor fallback for graphics pipeline | `vk_instance.cpp` and pipeline cache support unavailable extension | `vk_instance.cpp` already checks optional `VK_KHR_push_descriptor`; `vk_pipeline_cache.cpp` already uses `DescriptorHeap` | ALREADY PRESENT; leave untouched |
| Color/MSAA/depth blit descriptors | `src/video_core/texture_cache/blit_helper.cpp`: conditional `pushDescriptorSetKHR` or `DescriptorHeap` for both color/depth image operations | `blit_helper.cpp` created push-only layout and used push descriptors twice without fallback | **PORTED** conditional descriptor layout and GPU-tick-safe ordinary set bindings on both paths |
| Final image postprocessing descriptors | `src/video_core/renderer_vulkan/host_passes/pp_pass.cpp`: native descriptor-set fallback for composition | `host_passes/pp_pass.cpp` called `pushDescriptorSetKHR` unconditionally | **PORTED** ordinary sampled-image set, owned until the present GPU timeline completes |
| Shader resource table limits | `src/shader_recompiler/resource.h` uses 32 samplers and growable image/sampler lists; `vk_rasterizer.h` uses image + sampler capacity | Daedalus had 16 samplers, fixed 64-image descriptor table, fixed image bindings | **PORTED** 32 samplers, growable lists, combined 96-entry descriptor-image table |
| RectList / QuadList auxiliary shaders | `emit_spirv_quad_rect.cpp` | Same 339-line implementation apart from three declarations naming the fragment runtime type | ALREADY EQUIVALENT; no transplant |
| Mali detile scratch allocator | Public Bachata uses opt-in ring `BACHATA_MALI_GPU_OPT` | Daedalus already has a reusable, GPU-tick-aware `StagingBufferPool`; mechanisms differ | NEEDS hardware comparison, not blindly copy two allocation models |
| BCn texture transcode to ETC2 | Announced in RELEASE v0.2.5 | **Driver 26.3.1 already bundles the BCn-to-ETC2 implementation**, including encoder symbols; auto-selected on G615 when available. The older V3.2 package is a distinct implementation. | ALREADY PACKAGED IN DRIVER; not an emulator-side source port. Runtime correctness not verified on GoW3 |
| PanVK GPU tiler heap recycling | Announced in RELEASE v0.2.5 driver | Exact bundled V3.2 PanVK source pin `2a9358a` contains `patches/bachata-v3/0007-...` and `.so` exposes `PANVK_KBASE_SKIP_HEAP_OPS` | ALREADY PRESENT IN DRIVER; no duplicate emulator code required |
| Depth/stencil format fallback | Bachata public core `vk_instance.cpp::GetSupportedFormat` promotes unsupported D16S8 to D24S8 or D32S8 | Daedalus has the same promotion rules. Its extra image/view and readback implementation is not equivalent | SOURCE-EQUIVALENT PROMOTION; remaining render/readback correctness unresolved |
| Optional GoW3 GPU accelerated copy and predication | Bachata public core handles copy HLE with `vkCmdCopyBuffer`; it has no matching GoW3 predication reducer | Extra GoW3 multi-copy and predication compute pipelines assumed push descriptors | PORTED GUARD/FALLBACK: use Bachata-compatible copy path without push support and ordinary sets for optional predication |

## Implemented now

- `tile_manager.h`: lifetime-safe `DescriptorHeap`, fallback descriptor pool sizes,
  and `uses_push_descriptors` capability state.
- `tile_manager.cpp`: choose push-descriptor layout only when the device
  advertises at least three push descriptors; otherwise allocate/update
  ordinary sets and bind them in the existing asynchronous recording lambda.
- `blit_helper.{h,cpp}`: port the Bachata source's `DescriptorHeap`
  fallback to both color-to-MSAA-depth reinterpretation and MS image copy.
  Keep push descriptors when the extension/capability is present.
- `host_passes/pp_pass.{h,cpp}`: port the Bachata fallback in final-frame
  composition, using the **present scheduler** timeline for descriptor pool
  retirement; keep push-descriptor fast path on supported drivers.
- `vk_presenter.{h,cpp}`: provide `Instance` and present scheduler to the
  pass, and construct it *after* the schedulers so it is destroyed first.
- `shader_recompiler/resource.h` and `vk_rasterizer.h`: raise sampler
  table capacity to 32, use growable image/sampler lists and allocate
  a descriptor-image table for 64 images + 32 samplers, as in public Bachata.
  This changes real resource binding capacity, not capture/logging.
- `vk_shader_hle.cpp`: preserve the Bachata copy-buffer implementation on
  devices without 3 push descriptors; skip optional multi-copy compute dispatch.
- `vk_predication.{h,cpp}`: when the optional GoW3 predication compute reducer
  is enabled on a non-push device, bind an ordinary, GPU-tick-owned descriptor set.
- No changes to Adreno's supported push-descriptor path.
- No automatic render-pass captures or driver substitution.

## Next release gate

Build the remaining source changes once, in a consolidated native CI run.
Native compilation and one Mali device test are separate requirements.
Do not claim that the inaccessible Bachata RELEASE 0.2.5 core has been fully
reproduced or that GPU output is fixed merely because the APK compiles.
No additional renderer-diagnostic APKs should be issued.
