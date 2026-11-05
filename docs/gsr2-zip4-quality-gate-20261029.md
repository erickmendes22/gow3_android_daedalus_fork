# GoW III GSR2: native correspondence and jitter quality gate (2026-10-29)

## Captured evidence

Source: `GodOfWar3-GSR2-Input-Motion-Depth-Output (4).zip` (local diagnostic only, not committed).
CUSA01623 1.02, flips 6451-6456, 640x360 original input, 1280x720 reconstructed output.
All six captures are successful temporal dispatches with reset=0 and native depth available.
The complete source includes the world, actors, effects **and HUD**; the early pre-HUD candidate is incomplete (it omits foreground actors/effects).

- Model-camera motion median ranges approximately (-1.48,-0.15) to (-1.74,-0.18) *render pixels*.
- Native image translation from phase-correlation of static scenery measures roughly 0.01-0.03 pixel per consecutive frame.
- Warping the previous native input with those model vectors increases RGB disagreement ~10.4-12.9x relative to the unwarped correspondence.
- In one static scene region, reconstructed-image frame-to-frame differences are 2.19-6.32x the input differences (comparison made at equal 640x360 resolution).
- Native-to-native five-tap YCoCg matching on 15k sample positions per pair chooses zero displacement for about 96-97% of pixels; about 99% have match error below 0.002. These observations are specific to this near-static capture, **not** a motion-vector correctness certificate for other gameplay.

## Implemented experimental changes

- Preserve the genuine previous packed native YCoCg input in a separate persistent GPU image; update it only after the current upscale has consumed the older image.
- Match five-tap neighborhoods between two **native** inputs. Do not match against the already reconstructed history, which feeds ghosting/aliasing back into subsequent motion estimates.
- Reject invalid/ambiguous correspondence locally; keep actual Qualcomm temporal history and its previous-frame reconstruction active on valid pixels.
- Apply raster jitter to verified native-resolution depth-tested forward scene passes, even when they use a different depth attachment from the camera's last selected depth. Keep display buffers, UI draws without depth, and mismatched sizes outside this path.
- Avoid TextureCache image lookups on ordinary draws when the guarded direct GSR2 path is not active.

## Quality and release gate

This is NOT a visually verified fix. It is a separate experimental branch, not a release or known-good APK.
Shader SPIR-V compilation and host regression tests alone do not prove Android native C++ compilation, correct motion on moving actors, stable jitter, GPU performance or sharp output.
Do not reintroduce any old blurred/upscaled APK as a replacement.

Before labeling a release corrected, compare same-flip input/motion/depth/output on the device: check static scene shimmer, temporal sharpness, moving objects/particles, transparent effects, text/HUD and GPU time. If the native input still contains an unjittered scene or HUD within temporal history, correct that **upstream** of further image sharpening or postprocessing.
