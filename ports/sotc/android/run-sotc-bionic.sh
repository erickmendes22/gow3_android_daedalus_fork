#!/system/bin/sh
# SotC Bionic/FEX launcher, separate from the God of War III launcher.
set -eu
files=${FXD_FILES:?FXD_FILES is required}
base="$files/sotcport"
runtime="$base/arm64"
python="$runtime/python/bin/python3.13"
probe="$runtime/bin/sotc-probe"
game=${SOTC_GAME_DIR:-$base/game}
out="$base/sotc-out"
upstream="$base/scripts/sotc-upstream"
prepare="$base/scripts/sotc_prepare_game.py"
[ -x "$probe" ] || { echo "SotC Bionic native loader missing" >&2; exit 2; }
[ -f "$runtime/lib/libbbgpu.so" ] || { echo "SotC Vulkan library libbbgpu.so missing" >&2; exit 2; }
[ -x "$python" ] && [ -f "$prepare" ] && [ -f "$upstream/scripts/prepare.py" ] ||
    { echo "SotC game preparation scripts missing" >&2; exit 2; }
[ -f "$game/eboot.bin" ] && [ -f "$game/sce_sys/param.sfo" ] ||
    { echo "SotC dump requires eboot.bin and sce_sys/param.sfo" >&2; exit 2; }

export HOME="$files/home/sotcport" TMPDIR="$base/tmp" XDG_RUNTIME_DIR="$base/tmp"
export SOTC_PORT=1
export PATH=/system/bin LD_LIBRARY_PATH="$runtime/lib:$runtime/python/lib"
export PYTHONHOME="$runtime/python" PYTHONPATH="$base/scripts" PYTHONUTF8=1
export FEX_APP_CONFIG_LOCATION="$HOME/.fex-emu/"
export FEX_APP_DATA_LOCATION="$HOME/.fex-emu/"
export FEX_APP_CACHE_LOCATION="$HOME/.cache/fex-emu/"
mkdir -p "$TMPDIR" "$HOME/.fex-emu" "$HOME/.cache/fex-emu" "$base/user" "$base/logs" "$out"
# GPU pass dumps remain available on demand but are not forced at launch.
# Automatic volumetric-fog capture was unrelated to the missing geometry.
# Do not alter SOTC_DUMP/SOTC_AUTO_GPU_DUMP_AFTER supplied by the caller.
export SOTC_GPU_DUMP_DIR="$base/logs/gpu_capture"

chip=$("$runtime/bin/kgsl-chip-id" 2>/dev/null || true)
driver=${GOW3_BIONIC_DRIVER:-auto}
case "$driver" in
  auto)
    case "$chip" in
      0x44??????)
        # Prefer the validated GameHub driver on supported Android 14+
        # only when the exact driver is genuinely bundled in the APK.
        sdk=$(/system/bin/getprop ro.build.version.sdk 2>/dev/null || echo 0)
        if [ "${sdk:-0}" -ge 34 ] && [ -f "$runtime/drivers/gamehub-dd/libvulkan_freedreno.so" ]; then
            driver=gamehub-dd
        else
            driver=gen8
        fi ;;
      0x07??????|0x43020[01]00|0x43030b00|0x43050a01|0x43050b00|0x43051401)
        driver=adreno7xx ;;
      *) driver=system ;;
    esac ;;
  gen8|adreno7xx|gamehub-dd|system|custom) ;;
  *) echo "Invalid SotC Vulkan driver" >&2; exit 2 ;;
esac
if [ "$driver" = gen8 ] || [ "$driver" = adreno7xx ] || [ "$driver" = gamehub-dd ]; then
    export GOW3_VULKAN_DRIVER="$runtime/drivers/$driver/libvulkan_freedreno.so"
    [ -f "$GOW3_VULKAN_DRIVER" ] || { echo "Bundled SotC Vulkan driver missing" >&2; exit 2; }
elif [ "$driver" = custom ]; then
    custom=${GOW3_CUSTOM_VULKAN_DRIVER:-}
    case "$custom" in "$files"/gpu-drivers/*/*.so) ;;
      *) echo "Custom driver path is not allowed" >&2; exit 2 ;;
    esac
    [ -f "$custom" ] || { echo "Custom Vulkan driver missing" >&2; exit 2; }
    export GOW3_VULKAN_DRIVER="$custom"
    export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:${custom%/*}"
else
    unset GOW3_VULKAN_DRIVER
fi

# Geometry correctness on Turnip: the Adreno 830 is running a generated
# barycentric geometry shader. Mesa's multi-position shader optimization can
# produce stretched/repeated polygons on this path. TU_DEBUG=nomultipos is
# consumed by Turnip before VkCreateDevice and sets IR3 no_multi_pos.
# Only change bundled Mesa drivers, never the proprietary Vulkan system driver.
# Preserve any existing comma-separated TU_DEBUG choices from the launcher.
case "$driver" in
  gen8|adreno7xx)
    case ",${TU_DEBUG:-}," in
      *,nomultipos,*) ;;
      *) TU_DEBUG="${TU_DEBUG:+$TU_DEBUG,}nomultipos"; export TU_DEBUG ;;
    esac
    echo "SotC Turnip vertex integrity: nomultipos requested; TU_DEBUG=$TU_DEBUG"
    ;;
esac

export GOW3_ANDROID_INPUT=1 GOW3_PAD_FILE="$base/android-pad.state"
export GOW3_PAD_QUIET=1 GOW3_IME_FILE="$base/ime.request"
export GOW3_AUDIO_FIFO="$base/audio.fifo"
export GOW3_PRESENT_SOCKET="$base/present.sock"
export SOTC_PRESENT_SOCKET="$GOW3_PRESENT_SOCKET"
export SOTC_SCREEN_W=${SOTC_SCREEN_W:-1280} SOTC_SCREEN_H=${SOTC_SCREEN_H:-720}
export SOTC_VSYNC=${SOTC_VSYNC:-1}
# AjncSystem's native TAA resolve shader 0xa402ddac uses SRT dword 42 bit 0
# to blend the previous scene. On Adreno this makes previous geometry appear
# as dragged ghosts after the barycentric fallback restored materials.
# 1 = no temporal history blend; exposure, tonemap and stencil remain intact.
# Separate SotC-only setting; no change to Wave32, texture cache or GoW3.
export SOTC_TAA_OFF=${SOTC_TAA_OFF:-1}
case "$SOTC_TAA_OFF" in
    0) echo "SotC native TAA: temporal history enabled (comparison)" ;;
    1) echo "SotC native TAA: temporal history disabled (no old frames)" ;;
    *) echo "SotC native TAA: expected 0/1" >&2; exit 2 ;;
esac
# Per-game GPU readback mode: 0 Disabled / 1 Relaxed / 2 Precise.
# The default 2 preserves the previous behavior.
export BB_READBACKS=${BB_READBACKS:-2}
case "$BB_READBACKS" in
  0) echo "SotC readback: Disabled (experimental, stale graphics possible)" ;;
  1) echo "SotC readback: Relaxed (experimental, stale data possible)" ;;
  2) echo "SotC readback: Precise (default)" ;;
  *) echo "Invalid SotC BB_READBACKS=$BB_READBACKS" >&2; exit 2 ;;
esac
# Native SotC precise readback streaming, only pages marked GPU modified.
# Reuses the original synchronization and heap guards; 512KiB bounded cap.
export SOTC_RB_STREAM=${SOTC_RB_STREAM:-1}
export SOTC_RB_STREAM_MAX_KB=${SOTC_RB_STREAM_MAX_KB:-512}
case "$SOTC_RB_STREAM" in 0|1) ;; *) echo "Invalid SOTC_RB_STREAM" >&2; exit 2 ;; esac
case "$SOTC_RB_STREAM_MAX_KB" in 512) ;; *) echo "Invalid SOTC_RB_STREAM_MAX_KB" >&2; exit 2 ;; esac
if [ "$BB_READBACKS" != "2" ]; then export SOTC_RB_STREAM=0; fi
echo "SotC readback streaming: enabled=$SOTC_RB_STREAM max_kib=$SOTC_RB_STREAM_MAX_KB mode=$BB_READBACKS"
# Independent asynchronous GPU readback execution toggle.
export SOTC_RB_ASYNC=${SOTC_RB_ASYNC:-0}
# Upstream's 32 MiB/frame texture upload budget defers large first-use textures
# and explicitly fills those images with zero texels (black) until a later flip.
# SotC Android prioritizes complete materials over area-transition frame time:
# upload the actual texture before it is sampled, never its zero-fill placeholder.
# 0 is a documented and implemented disable value in texture_cache.cpp.
export SOTC_UPLOAD_BUDGET_MB=0
# Bachata S4+ 0.2.7 game effects; strictly verified before BBPATCH2 creation.
# These options do not change Wave64, tessellation or the working Turnip.
export SOTC_BACHATA_PERF=${SOTC_BACHATA_PERF:-bloom,blur}
echo "SotC Bachata game performance patches: $SOTC_BACHATA_PERF"
# The original PC port defaults to texture quality High; it sets
# SOTC_LOD_LINGER=1, unlike the renderer's own low-detail fallback (0).
# With 0, even a recently sampled counter bank reports mip 15 (unused), so
# the game never streams high-resolution mips (blurry ground/rocks, missing
# waterfall/black water). Our 0.1.15 device log CONFIRMED "texture level off".
# Preserve safe mip 2 and pool-pressure downgrade (8%) rather than Maximum.
export SOTC_LOD_LINGER=${SOTC_LOD_LINGER:-1}
export SOTC_LOD_LEVEL=${SOTC_LOD_LEVEL:-2}
export SOTC_LOD_POOL_LOW=${SOTC_LOD_POOL_LOW:-8}
echo "SotC texture streaming: high/stable (LOD linger=$SOTC_LOD_LINGER mip=$SOTC_LOD_LEVEL pool_low=$SOTC_LOD_POOL_LOW)"
echo "SotC texture integrity: zero-fill upload deferral disabled"
# Recover dynamic descriptor arrays in material/lighting fragment shaders.
# The vertex shader array path stays excluded (known upstream GPU hang).
export SOTC_ANDROID_FRAGMENT_TSHARP=1
echo "SotC render coherence: mode=$BB_READBACKS async=$SOTC_RB_ASYNC"
# Rendering correctness first on Android: the PC backend can return nullptr
# for geometry draws while asynchronous shaders/pipelines are still being
# compiled (vk_pipeline_cache.cpp). With a cold shader cache this produces
# missing geometry and transient flicker, not merely poor FPS.
# Async graphics pipeline build test (OFF by default). The PC renderer may
# temporarily skip >6-index draws whose pipeline is still compiling; this
# can cause missing objects/pop-in, so leave OFF unless testing A/B.
# Translation and boot preload stay synchronous to isolate this one change.
export SOTC_ASYNC_SHADERS=${SOTC_ASYNC_SHADERS:-0}
# Correctness guard is intentionally ON even if experimental async is enabled.
# Shader stages are materialized before draws; graphics pipeline compilation
# may use a worker, but the draw waits instead of disappearing that frame.
# No extra option is exposed in the UI.
export SOTC_NO_DROPPED_DRAWS=1
export SOTC_ASYNC_TRANSLATE=0
export SOTC_ASYNC_PRELOAD=0
# Separate compute deferral. With recording thread + graphics workers this
# would otherwise default ON and silently alter the shader-only A/B test.
export SOTC_ASYNC_COMPUTE=${SOTC_ASYNC_COMPUTE:-0}
# Safe AHB fullscreen transfer optimization; defaults ON only when the blit
# overwrites the entire output surface; letterbox retains clear+barrier.
export SOTC_PRESENT_FULL_BLIT=${SOTC_PRESENT_FULL_BLIT:-1}
echo "SotC Vulkan compute async=$SOTC_ASYNC_COMPUTE present fullscreen blit=$SOTC_PRESENT_FULL_BLIT"
echo "SotC experimental async graphics pipelines: $SOTC_ASYNC_SHADERS (1 may cause temporary missing geometry)"
# Native A/B for stale descriptor reuse vs Vulkan command recording.
# Keep Wave32, TAA, texture LOD, shaders and readbacks unchanged.
# Android host Vulkan command-state memoization only; unlike SOTC_FAST_BIND
# these do not skip guest resource/buffer/texture tracking.
# Set any one to 0 for a reversible comparison without losing the good Turnip.
export SOTC_PIPELINE_BIND_MEMO=${SOTC_PIPELINE_BIND_MEMO:-1}
export SOTC_VERTEX_INPUT_MEMO=${SOTC_VERTEX_INPUT_MEMO:-1}
export SOTC_DESCRIPTOR_SLOT_REUSE=${SOTC_DESCRIPTOR_SLOT_REUSE:-1}
echo "SotC host Vulkan fastpaths: pipeline=$SOTC_PIPELINE_BIND_MEMO vertex=$SOTC_VERTEX_INPUT_MEMO descriptor_slots=$SOTC_DESCRIPTOR_SLOT_REUSE"
# Real CPU bottleneck optimization. The CP still refreshes flattened SRTs
# from live guest memory, validates exact shader specialization inputs and
# chooses the same module; draw receives an exact per-op snapshot via swap.
# OFF restores the 0.1.27 path with the original full data copies.
export SOTC_STAGE_SPEC_MEMO=${SOTC_STAGE_SPEC_MEMO:-1}
export SOTC_STAGE_SNAPSHOT_SWAP=${SOTC_STAGE_SNAPSHOT_SWAP:-1}
export SOTC_REG_SNAPSHOT_MEMO=${SOTC_REG_SNAPSHOT_MEMO:-1}
# Experimental: OFF until validated on real SotC gameplay.
export SOTC_RT_MEMO=${SOTC_RT_MEMO:-1}
# Native Bionic guest-memory region cache (64 writes journal, 512 direct slots).
# 0 restores generation-only eight-entry cache and all old lock checks.
export SOTC_VM_RANGE_CACHE=${SOTC_VM_RANGE_CACHE:-1}
case "$SOTC_VM_RANGE_CACHE" in
  0|1) ;;
  *) echo "Invalid SOTC_VM_RANGE_CACHE (expected 0/1)" >&2; exit 2 ;;
esac
echo "SotC CPU hot path: shader_spec_exact=$SOTC_STAGE_SPEC_MEMO stage_snapshot_swap=$SOTC_STAGE_SNAPSHOT_SWAP reg_snapshot_memo=$SOTC_REG_SNAPSHOT_MEMO"
echo "SotC Bionic VM: interval cache=$SOTC_VM_RANGE_CACHE; reserve logging capped to 16 (BB_MEMORY_LOG=1 overrides)"
# A/B performance *diagnostics*, not a performance tweak. The upstream
# stats switches are getenv-presence based: setting either one to "0"
# would STILL activate it. Unset both unless explicitly selected in UI.
if [ "${SOTC_PERF_PROFILE:-0}" = "1" ]; then
    export SOTC_FPS=1
    export SOTC_DRAW_SPLIT=1
    unset SOTC_CMD_STATS
    echo "SotC CPU/GPU frame profiling ON: five-second SOTC FPS/FRAMES/DRAW SPLIT counters"
else
    unset SOTC_FPS SOTC_DRAW_SPLIT SOTC_CMD_STATS
fi
export SOTC_FAST_BIND=${SOTC_FAST_BIND:-0}
export SOTC_RECORD_THREAD=${SOTC_RECORD_THREAD:-0}
echo "SotC GPU A/B: fast_bind=$SOTC_FAST_BIND record_thread=$SOTC_RECORD_THREAD rb_async=$SOTC_RB_ASYNC (0=conservative)"
if [ "$SOTC_ASYNC_SHADERS" = "1" ]; then
  echo "SotC render completeness: experimental async graphics pipeline build; queued geometry draws can be skipped until ready"
else
  echo "SotC render completeness: synchronous graphics shaders and pipelines; no async draw skips"
fi
# Fragment barycentric interpolation now selects a capability-gated
# auxiliary GS on Adreno where both native extensions are missing.
# Old shaders have no matching GS inputs and MUST NOT be reused.
# Descriptor-array lowering also covers fragment shaders.
# The IR lowering changed after the early 0.1.4 SRT implementation.
# Pipeline keys do not encode the lowering revision or the auxiliary GS interface:\n# keep old compiled pipeline caches isolated; never reopen old SPIR-V
# or SRT walkers even if the game hash and Vulkan profile match.
# Keep both subgroup variants separate and preserve --user "$base/user" saves.
case "${SOTC_ADRENO_WAVE32:-0}" in
    1) sotc_gpu_profile=wave32 ;;
    *) sotc_gpu_profile=wave64 ;;
esac
export BB_GPU_USER_DIR="$base/gpu-user-srt-phi7-tess-gs-position-turnip-nomultipos-$sotc_gpu_profile/lds-meta1"
mkdir -p "$BB_GPU_USER_DIR"
echo "SotC GPU cache revision: srt-phi7-tess-gs-position-turnip-nomultipos; profile=$sotc_gpu_profile; directory=$BB_GPU_USER_DIR"
case ${1:-game} in
    vulkan) exec "$probe" --vulkan-only ;;
    game) ;;
    *) echo "Unknown SotC launcher mode" >&2; exit 2 ;;
esac
echo "SotC requested guest render: ${SOTC_RENDER:-1280x720}; Android output: ${SOTC_SCREEN_W}x${SOTC_SCREEN_H} (output remains 720p)"
set -- "$python" "$prepare" --upstream "$upstream" --game-dir "$game" \
    --out "$out" --render "${SOTC_RENDER:-1280x720}" --modes "${SOTC_MODES-fps60game}" \
    --cvars "${SOTC_CVARS:-doIndexBufferCulling=0 doSunShadowIndexBufferCulling=0}" \
    --perf "$SOTC_BACHATA_PERF"
if [ -n "${SOTC_SYS_MODULES:-}" ]; then
    set -- "$@" --sys-modules "$SOTC_SYS_MODULES"
fi
"$@"
for item in boot-linked.bin content.bin patches.bin sotc-cpu.bin; do
    [ -s "$out/$item" ] || { echo "Missing prepared SotC file: $item" >&2; exit 3; }
done
# FEX implements guest x86 SSE4a; PC-only Xbyak CPU patchers are not native ARM64.
set -- "$probe" "$out/boot-linked.bin" \
    --content-profile "$out/content.bin" --patches "$out/patches.bin" \
    --app0 "$game" --user "$base/user" --timeout "${SOTC_TIMEOUT:-0}"
if [ -s "$out/cmdline.bin" ]; then
    set -- "$@" --sotc-cmdline "$out/cmdline.bin"
fi
echo "SotC Bionic: title from original BBPROBE5, driver=$driver, FEX ARM64"
cd "$base"
exec "$@"
