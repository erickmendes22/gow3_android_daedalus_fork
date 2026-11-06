# G720 Mali vs Android Adreno concurrency — experimental parity

Code audit: Android Adreno defaults: 8 in-flight Vulkan submits, 2
compiler workers, **0 draw-preparation workers**. The prior
"Adreno normally uses draw prep workers" claim was incorrect.
PanVK override before change: 2 in-flight, 1 compiler worker,
0 draw preparation workers, synchronous graphics first-use.

The isolated Mali tester now uses 8/2/0 to match actual Android
Turnip defaults, with no change to recorded fence/label ordering,
memory copy, AHB presentation, GPU-dirty alias guards, or Image pool.
An opt-out `GOW3_VK_MAX_IN_FLIGHT=2` restores queue depth,
`GOW3_GPU_COMPILER_WORKERS=1` restores prior compiler budget.

For first-use draws Mali now has `GOW3_MALI_ASYNC_DRAW_WAIT=1`:
async jobs can compile shaders and graphics on the existing background
workers, but the **consuming draw waits for the compiled result**.
Unlike the conventional Adreno async option this cannot silently
drop missing scene, depth or shadow draws. Worker queue overflow
falls back to original synchronous compilation. `=0` reverts
first-use compilation to the GPU thread without waiting for workers.

Risk: larger queue can temporarily increase GPU allocation and cause
stutters or OOM on PanVK even when total throttle waits are small.
No device FPS benefit is claimed until same-driver/scene A/B. Keep
`GOW3_PREP_WORKERS=0`: that is already Android Adreno parity and
background preparation creates costly speculative PM4 copies.
