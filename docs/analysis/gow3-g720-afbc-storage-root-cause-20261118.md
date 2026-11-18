# GoW III Mali G720 — structural performance regression candidates (2026-11-18)

## G720 steady scene and gate

G720 MC7, warm shader/pipeline scene, 960x540, 2,567 draws per frame, 5.2727 FPS => 189.65 ms/frame. **More than 2x FPS requires less than 94.83 ms/frame**, removing **more than 94.83 ms from the *actual* GPU/CPU critical path**. The existing `GPU-ticks blocked 82.1%` figure is host wait time and is not a GPU-bottleneck classification.

## Confirmed source-level anti-pattern: PanVK AFBC disabled by universal STORAGE image usage

Our prior `gpu/shadps4/video_core/texture_cache/image.cpp::ImageUsageFlags()` added `VK_IMAGE_USAGE_STORAGE_BIT` to *every* non-depth color VkImage, even guest images used only as framebuffers and texture inputs. PanVK's `panvk_image_can_use_afbc()` rejects images with `VK_IMAGE_USAGE_STORAGE_BIT`; our generic renderer flag therefore prevented AFBC on eligible Mali color render targets. This is **proven from the source**, not a proven percentage FPS cause.

- PanVK driver source: https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/47e8d5c1846b219ea6d30a5ab4b6c608c8bcd1e7/src/panfrost/vulkan/panvk_image.c
- Arm GPU Best Practices, page 84: https://documentation-service.arm.com/static/67a62b17091bfc3e0a947695
- Khronos AFBC sample: https://docs.vulkan.org/samples/latest/samples/performance/afbc/README.html (788 -> 528.6 MiB/s bandwidth, ~33% reduction in one *different* scene; **NOT** a GoW3 FPS gain).

### Implemented conservative Mali policy on research branch

- `ImageInfo::props.needs_storage` is true for guest shader `is_written` resources; pure color attachments and read-only textures remain false.
- On PanVK Android only, eligible 2D non-depth/non-BC, 1xMSAA, <=32bpp color images omit universal STORAGE usage, making them **AFBC candidates**. Other GPUs and excluded shapes preserve the old usage flags.
- If a guest storage descriptor later references an AFBC-eligible image created as a render target, `TextureCache::FindImage` rejects stale non-storage cache hits and calls `ExpandImage` to allocate a true STORAGE-capable image and **copy existing GPU pixels**, so imageStore remains legal.
- `GOW3_MALI_AFBC_COLOR_RT=1` is the **default** in the PanVK launcher; `=0` restores old all-STORAGE allocation policy. The lightweight log has `afbc_candidates` and `afbc_storage_upgrades` counts. Candidate count does **not** confirm actual AFBC compression: format, modifier support and driver settings matter.

## Confirmed diagnostic blind spot and optimization: image rebind

In `UniqueImage::Create`, `RebindRetiredImageMemory` is attempted before `image_vk_allocate` timing; a failed rebind sometimes created/destroyed a driver VkImage, then VMA created another. The previous telemetry did **not** attribute the first driver call. Implemented `image_rebind_probe` stage and `rebind_candidates`, `rebind_incompatible`, `rebind_success`, `rebind_fast_reject` counters. A bounded per-thread memo of Vulkan memory requirements for *identical no-pNext image descriptions and VkDevice* now excludes definitely incompatible completed retired VMA blocks **before** creating a duplicate VkImage, while preserving original requirements verification and fallback for eligible images. The memo is invalidated when the image allocator is flushed during device destruction.

The rebind fix primarily targets **allocation spikes**, not 2,500-draw steady state. Do not count its peak saving as per-frame FPS improvement.

## Shader and synchronization candidates already in branch

- Read-only guest U32/F32 shader data can now be `UniformBuffer` rather than `StorageBuffer` for 4 B–16 KiB buffers. It is on by default (`GOW3_UBO=2`), with `=0` rollback, and safely cache-versioned. GoW3 PR #9 measured Adreno improvement (22.2 -> 29.5 FPS) **not tested on Mali**.
- `MALI_CAUSAL_COUNTS` records real RectList/QuadList, tessellation/geometry stages, barrier-triggered renderpass splits and scope of hazards. The GoW3 Rect/Quad pipeline generates auxiliary TCS/TES and PanVK can run expensive emulated tessellation; counts are still needed to determine whether this is common enough to matter.
- Driver PanVK barriers and tiler heap renewals must retain dependencies; no blanket removal or speculative inflated queue depth.

## Performance calculation is not a device prediction

For base T=189.65 ms, target <94.83 ms. In Khronos' unrelated AFBC example, 33% **bandwidth** reduction would imply a *maximum* 1.49x FPS only **if this entire GoW3 frame were limited by precisely that bandwidth**. Multiplying that by the ~1.33x **Adreno** UBO improvement gives about 1.98x in an unjustifiably ideal combination, **not established on G720**. The actual Mali performance ceiling cannot be claimed without a matched same-scene A/B or GPU timestamp breakdown.

**Build rule:** continue native safety compilation on this branch, but do not create a release APK until an evidence-supported >2x same-scene estimate, per the user's condition. No Android device execution or observed FPS result was available for these changes.
