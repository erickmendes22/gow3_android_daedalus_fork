# GSR2 Android — ZIPs (8) and (9): residual temporal shimmer (2026-10-30)

## Scope

User reports a clear improvement after disabling unverified native Halton raster jitter, but significant remaining instability. These captures are from CUSA01623 01.02, experimental Bionic native 640x360 -> 1280x720 GSR2.

This document separates **observed** original-image displacement from speculative camera/shader provenance, to prevent more unverified source switching.

## ZIP (8): true guest draw stages

- 42 samples of the same VideoOut guest address (0x10b9be8000); captures are tied to a single confirmed presented flip.
- Draw 1 and draw 16–28 are byte-identical. The first new visible effects occur after draw 28 (3.097% of pixels change at draw 29), followed by smaller changes around draws 30–38.
- Additional effect contributions appear around draws 52–80. The final presented image differs from stage 80 in nearly all pixels because it includes color/blur postprocessing, a major weapon effect, and HUD.
- Therefore using the very first VideoOut draw as a “completed scene” is incorrect. Switching to a later fixed draw is **not yet validated**, either: the last image contains other post-effects and HUD.
- Captured fragment programs around the observed first transition: 0x30e354c9fa8dbe71 (next drawn after stage 29). Later observed program 0x30cea6fbbba4f532. These are identifiers only; do not label as HUD/particles without shader disassembly.

## ZIP (9): six actual temporal GSR2 frames

- Frames f000–f005 have reset=0 and real depth, from consecutive flips 7244–7249.
- In every captured frame, `input` equals `post_scene` byte for byte; it is not the fully graded `videoout` output.
- Jitter reported as (0, 0), preserving the earlier stabilization.
- Direct 640x360 source-image correlation (central/lower and upper scene patches) finds ≈ +3 source-pixel X shift, with Y ≈ 0 for f000→f001 and ≈ +1 for subsequent frames. Direction here means the **previous image sample coordinate relative to current**.
- Phase correlation estimates fractional magnitude ≈ 2.7–3.6 native px horizontal depending on patch/frame. Integer-only history sampling introduces a further up-to-half-pixel residual; phase-correlation estimates in occluded or moving foreground are not reliable camera ground truth.
- The captured synthetic model motion field varies dramatically across screen (often from negative X to positive X), so its raw values cannot be assumed valid global camera flow.
- The original `gsr2_upscale.comp` only tested 16 sparse 2D offsets, omitted both (3,0) and (3,1), and only expanded the search when `bestError > 0.0006`. That skipped measured matches and could pick (4,0) or (2,2) instead.
- CPU offline tests on the original frames found that adding missing offsets changes the selected correspondence in roughly 10–20% of sampled scene pixels (ROI and shader-cost approximation dependent). Separately, bounded quadratic refinement around the true integer neighbor reduced five-tap photometric loss in sampled areas. Neither metric proves on-device visual correction.

## Experimental code change

- Extend search to a symmetric 30-offset set including ±3 and mixed ±2/±1 offsets.
- Lower the search entry condition to 0.00012, with exact nonnegative center-tap loss lower-bound pruning to avoid most unnecessary 5-tap lookups.
- On validated original-native history matches only (nonzero offset, error <0.0015), fit bounded ±0.5-pixel local parabolic refinements. These adjust previous **history UV**, not current rasterization. Flat/ambiguous neighborhoods remain integer.
- **Keep zero scene/Qualcomm jitter in reduced-raster mode** until native subpixel raster response is proven. Preserve previous Native AA behavior, the actual motion/depth validity gates, and UI compositor.
- Source tests and SPIR-V compilation are necessary checks, not confirmation of runtime Vulkan performance/quality.

## Remaining work / no premature claims

1. Verify stable on-device GSR2 output and performance; current patch may alter GPU cost.
2. Evaluate what portion of remaining shimmer is newly-added weapon effects/post-composition, not camera motion. Scene-before-effects and final VideoOut are different render stages.
3. Never claim image source selection correct solely because a flip address matches. Full effects, tone grade, and HUD may arrive after the sample.
