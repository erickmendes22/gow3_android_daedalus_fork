# SotC Android render comparison: Bachata S4+ vs Daedalus

Analysis: 2026-10-31. Scope: visible missing textures, silhouettes, white flashes.
Evidence: Android log ShadowOfTheColossus-Logs-20261031-071233.zip and three
screenshots from the Adreno 830; compare source, NOT presumed binary behavior.

## Wave32: keep, do not disable

The screen with Wave32 requested retains silhouettes and background, whereas
turning the switch off yields extreme overexposure. The Android log reports
`requested=1`, physical `subgroupSize=64`, `min=32`, `max=64`, stages
`0x7fffffff`, but claims "inactive". That claim is generated before
`vk13_features` is assigned in `vk_instance.cpp::CreateDevice`, so it
is invalid as an effective-mode diagnostic. `stage_adreno_wave32.py` now logs
the selected shader compiler target and vertex/fragment/compute required
subgroup sizes *after* the feature flags are initialized. User selection,
runtime behavior and per-mode shader caches are unchanged.

## Bachata: patches that already have counterparts

Investigated:
- erickmendes22/Bachata-S4-Plus branch `feature/sotc-r35-array-lod-wip`:
  `port_sotc_lod.py`, `port_sotc_gpu_sync.py`,
  `README-R35-GRAPHICS-INVESTIGATION.md`.
- SotC PC fork `AjncSystem/ShadowOfTheColossus-PC` staged into
  `out/sotc-android/gpu` by `stage_renderer.py`.

Bachata's SotC experimental LOD fix:
- Marks each bound scalar TSharp AND bindable elements of TSharp arrays;
- Returns PM4 GET_LOD_STATS for 256 banks and mip 2;
- Drops stale GPU-modified ranges on memory unmap (opt-in in Bachata port).

The AjncSystem renderer ALREADY has the equivalent or more developed paths:
- `vk_rasterizer.cpp::BindTextures` handles LOD counter marks for scalar
  AND each bindable array element;
- `liverpool.cpp::GetLodStats` calls `SotcLod::Collect` and writes feedback
  into guest memory (default enabled);
- `vk_rasterizer.cpp::UnmapMemory` already defaults to
  `buffer_cache.DropGpuModified`, avoiding stale readback into freed memory;
- `resource_patching_pass.cpp` already has dynamic TSharp arrays in COMPUTE
  shaders (reflection probe path).

**Important log nuance:** `SOTC LOD: texture level off` means the optional
"linger/high-quality" texture-level setting is off (zero reports of linger).
It DOES NOT establish that PM4 LOD statistics are disabled; the default
`SOTC_LOD_STATS` is enabled. Do not force mip 0/1 or unconditional high-LOD
linger: the PC fork documents guest page-pool corruption in those modes.

## GPU readback scheduling: conservative Android compatibility

The Bachata SotC profile uses precise readbacks (mode 2), and the PC fork
already defaults to `BB_READBACKS=2` (`gpu/shim/core/emulator_settings.h`).
Thus simply switching relaxed->precise was NOT a missing fix. However, the
PC fork also enables a separate `SOTC_RB_ASYNC` path by default; it begins
the GPU readback on the command processor, waits for a GPU timeline tick,
and only then installs the copy. The user prioritizes correct textures over
FPS, so the Android SotC runner now explicitly sets `BB_READBACKS=2` and
`SOTC_RB_ASYNC=0`. The latter follows the PC fork's synchronous
`SendCommand<true>(flush_request)` path. This is a deliberate compatibility
trial based on a concrete scheduling difference, NOT proven to eliminate
the overexposure/flicker. Keep the Wave32 option intact for both A/B cases.

## Remaining known divergence

The Android SotC port uses a custom portable ARM64 SRT walker with dynamic
512-dword windows and the PC shader resource patcher. On the Adreno test
`Sharp source uses a runtime index` appears 16 times. An unresolved dynamic
resource cannot be bound as a valid image/sampler/buffer when the shader
requires a descriptor location determined at runtime. The existing PC workaround
handles some compute dynamic TSharp tables, but deliberately does NOT enable
the same array expansion in vertex shaders; the authors document a GPU hang
with vertex shader `0x9d6f9bf4`. Do not globally enable this workaround.

The Bachata R35 analysis documents 16 compiler errors for the optimized
binary with different opcodes; its source baseline differs from the shipped
binary. It is an experimental ELF and explicitly not an installable release.
Therefore, copying offsets/hooks from that binary into this renderer is unsafe.

## Next visual fix, not yet validated

Fix the unresolved ARM64 dynamic resource binding by stage/descriptor type,
keeping Wave32 functional. A conservative next patch must identify each failing
shader hash, resource type, and dynamic table length before changing the actual
descriptor-array lowering. Preserve the compute-only fallback and protect
against GPU hangs on vertex shaders. Evaluate synchronization only if captures
show frame-to-frame stale resource or missing barriers. Do not apply a brightness
clamp, don't turn Wave32 off, and don't claim texture correctness without
on-device comparison.

## Android texture upload integrity (0.1.15)

The pinned SotC PC renderer (`texture_cache.cpp`) defaults to a 32 MiB/frame
`SOTC_UPLOAD_BUDGET_MB` limit. Large first-use colour textures past that limit
are intentionally uploaded as zero-filled placeholders and retried on a later
frame. On Android this can look like missing black materials during area changes.
The Android runner now sets `SOTC_UPLOAD_BUDGET_MB=0`, the upstream's documented
off switch, so no texture is skipped or replaced by zeros by this budget path.
A frame may stall during first upload; preserve Wave32, GS barycentrics, TSharp
fragment arrays, readback coherence and original LOD. This removes one verified
source of intentionally missing texels; it does not prove all remaining missing
geometry or flicker is solved without a device comparison.

## SotC Android 0.1.16: validated auxiliary GS Position interface

Pinned upstream SotC renderer emits an auxiliary barycentric GS on Android
Adreno with a gl_PerVertex block declaring Position, PointSize, ClipDistance
and CullDistance, although the preceding vertex shader emits a standalone
Position BuiltIn. Android-only staging reduces the GS block to Position and
Invariant, removing unused, unwritten members while preserving all
material/texture varyings and barycentric interpolation. The actual generated
geometry SPIR-V was compiled and passed Khronos SPIRV-Tools Vulkan 1.2
spirv-val in successful GitHub Actions run 41220978037 (separate source
audit). Shader caches are segregated by the GS ABI revision (phi6).
The earlier verified no-zero-fill upload budget fix is preserved. This
source/IR verification is not a substitute for same-scene testing on Adreno.

## Android 0.1.17: regression confirmed on the phone and corrected in launcher

The 0.1.15 Android device log (2026-10-31 14:04:01; Adreno 830, Turnip
26.2.99, Wave32 active) explicitly prints `[TEXTURE] Texture level in use: Off`
and `SOTC LOD: texture level off`. Unlike earlier reports that assumed an
enabled PM4 GET_LOD_STATS handler was sufficient, the pinned SotC PC source's
default is `Linger=0`: `SotcLod::Collect` returns mip 15 (unused) for all
banks, *including those marked sampled that frame*. This leaves the game at
256x256 base textures, can produce black water and missing waterfall sheets,
and is an actual initialization mistake in the Android runner.

The PC launcher's High (stable) mode sets `SOTC_LOD_LINGER=1`, mip 2,
`SOTC_LOD_POOL_LOW=8`. The Android runner now initializes these three
values explicitly, retaining the same conservative page-pool pressure
protection rather than Maximum (which has documented guest allocator faults).
`SOTC_UPLOAD_BUDGET_MB=0` remains, so the streaming change is not obscured
by zero-filled placeholders. The source/default regression is tested.

The same 0.1.15 game command line included NO `r_motionBlurEnable=0`. The
Android UI exposed "Disable Motion Blur" but left it disabled by default.
Android now starts with `r_motionBlurEnable=0` by default, with a reversible
option for the user to restore original motion blur. The separate
`SOTC_TAA_OFF=1` remains and the Adreno barycentric GS Position repair
is retained. Motion blur suppression targets the visible long streaks; it
does not prove every earlier ghost is the game's motion blur.

Also observed: 16 `Sharp source uses a runtime index` warnings, still
not isolated to shader stage or source. Those may explain residual missing
materials and require per-shader evidence before unsafe descriptor array
changes; the vertex workaround is deliberately not enabled globally due
to a documented GPU hang in VS 0x9d6f9bf4.

Do not claim visual correctness until a same-scene Android run confirms it.
