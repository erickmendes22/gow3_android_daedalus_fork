#!/system/bin/sh
# Shadow of the Colossus native ARM64 AOT launcher, separate from God of War III.
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
# The strict AOT variant needs both the native CPU engine and the selected
# code library. An on-device rebuild is a separate non-game launch mode.
[ -f "$runtime/lib/libbbcpu.so" ] && [ -f "$runtime/lib/libgow3cpu.so" ] || {
    echo "SotC AOT CPU backend missing (do not silently start FEX)" >&2; exit 2;
}
# No copyrighted game code is packaged. On-device compilation is mandatory:
# the local libSotcAot.so is checked against this game's image and patches.
# During 'compile' mode the standalone bb-recomp tool runs without guest CPU.
export BB_AOT_MISS_LOG="$base/logs/aot-misses.log"

[ -f "$runtime/lib/libbbgpu.so" ] || { echo "SotC Vulkan library libbbgpu.so missing" >&2; exit 2; }
[ -x "$python" ] && [ -f "$prepare" ] && [ -f "$upstream/scripts/prepare.py" ] ||
    { echo "SotC game preparation scripts missing" >&2; exit 2; }
[ -f "$game/eboot.bin" ] && [ -f "$game/sce_sys/param.sfo" ] ||
    { echo "SotC dump requires eboot.bin and sce_sys/param.sfo" >&2; exit 2; }

export HOME="$files/home/sotcport" TMPDIR="$base/tmp" XDG_RUNTIME_DIR="$base/tmp"
export SOTC_PORT=1
export PATH=/system/bin LD_LIBRARY_PATH="$runtime/lib:$runtime/python/lib"
export PYTHONHOME="$runtime/python" PYTHONPATH="$base/scripts" PYTHONUTF8=1
mkdir -p "$TMPDIR" "$HOME" "$base/user" "$base/logs" "$out"
# The AOT-only launcher does not configure or execute any FEX runtime.
# GPU pass dumps remain available on demand but are not forced at launch.
# Automatic volumetric-fog capture was unrelated to the missing geometry.
# Do not alter SOTC_DUMP/SOTC_AUTO_GPU_DUMP_AFTER supplied by the caller.
export SOTC_GPU_DUMP_DIR="$base/logs/gpu_capture"

# Shadow of the Colossus is distributed with exactly one verified Vulkan
# driver. No silent fallback to system/Gen8/R1/R6/patched alternatives.
driver=${GOW3_BIONIC_DRIVER:-gamehub-dd}
[ "$driver" = gamehub-dd ] || {
    echo "Shadow of the Colossus requires bundled GameHub DD 26.3 Turnip" >&2; exit 2;
}
export GOW3_VULKAN_DRIVER="$runtime/drivers/gamehub-dd/libvulkan_freedreno.so"
[ -f "$GOW3_VULKAN_DRIVER" ] || {
    echo "Bundled GameHub DD Turnip missing from this APK" >&2; exit 2;
}
# Preserve TU_DEBUG geometry workaround used in the verified Adreno path.
case ",${TU_DEBUG:-}," in
  *,nomultipos,*) ;;
  *) TU_DEBUG="${TU_DEBUG:+$TU_DEBUG,}nomultipos"; export TU_DEBUG ;;
esac
echo "SotC GameHub DD 26.3 Turnip selected; TU_DEBUG=$TU_DEBUG"

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
export SOTC_RB_STREAM=1
export SOTC_RB_STREAM_MAX_KB=1024
case "$SOTC_RB_STREAM" in 0|1) ;; *) echo "Invalid SOTC_RB_STREAM" >&2; exit 2 ;; esac
case "$SOTC_RB_STREAM_MAX_KB" in 512|1024) ;; *) echo "Invalid SOTC_RB_STREAM_MAX_KB" >&2; exit 2 ;; esac
if [ "$BB_READBACKS" != "2" ]; then export SOTC_RB_STREAM=0; fi
echo "SotC readback streaming: enabled=$SOTC_RB_STREAM max_kib=$SOTC_RB_STREAM_MAX_KB mode=$BB_READBACKS"
# PC v0.71 T38 64KiB pool ownership / PC v0.72 speculative readbacks.
# The FEX probe disables fast readbacks if the release-call site is unverified.
export SOTC_POOL_OWNER=${SOTC_POOL_OWNER:-1}
export SOTC_RB_HOT=${SOTC_RB_HOT:-0}
case "$SOTC_POOL_OWNER:$SOTC_RB_HOT" in 0:0|0:1|1:0|1:1) ;; *) echo "Invalid pool owner/fast readbacks" >&2; exit 2 ;; esac
if [ "$SOTC_POOL_OWNER" != 1 ] || [ "$BB_READBACKS" != 2 ]; then SOTC_RB_HOT=0; export SOTC_RB_HOT; fi
echo "SotC PC v0.72: pool_owner=$SOTC_POOL_OWNER fast_readbacks=$SOTC_RB_HOT (verified site required; set SOTC_RB_HOT=0 to compare)"
# Independent asynchronous GPU readback execution toggle.
export SOTC_RB_ASYNC=1
# Measured PC v0.76 streaming paths, guarded by coherent staging / join on submit.
# 128 MiB idle large staging per memory type on Android, not PC's 256 MiB.
# PC #308 fastpath switches: only accepted values are 0 (old path) or 1.
# Keep these independent from the old experimental RT/PM4 optimizations.
export SOTC_DEPTH_FAST="${SOTC_DEPTH_FAST:-1}"
export SOTC_GBUFFER_FAST="${SOTC_GBUFFER_FAST:-1}"
case "$SOTC_DEPTH_FAST:$SOTC_GBUFFER_FAST" in 0:0|0:1|1:0|1:1) ;;
  *) echo "Invalid PC depth/G-buffer fastpath switches" >&2; exit 2 ;;
esac
echo "SotC PC #308 fastpath: depth=$SOTC_DEPTH_FAST gbuffer=$SOTC_GBUFFER_FAST"
export SOTC_STAGING_LARGE_POW2=1
# PC 0.74 exact depth/G-buffer port: keep the tested Android 128 MiB
# numeric reserve until the newer 0.76 allocator policy is merged. The PC
# 0.74 code parses numeric values and would treat `auto` as zero.
export SOTC_STAGING_LARGE_KEEP_MB=${SOTC_STAGING_LARGE_KEEP_MB:-128}
export SOTC_BUF_ASYNC_KB=256
# PC GPU hotpaths on mobile, while keeping precise guest readbacks.
export SOTC_FILL_HLE_GPU=1
export SOTC_TEX_ASYNC_KB=512
# Compute translation ahead of dispatch, and verified negative VMA caching.
export SOTC_COMPUTE_PREFETCH=1
export SOTC_VM_GAP_CACHE=1
export SOTC_COPY_BATCH=1
export SOTC_RB_NARROW=64
echo "SotC PC streaming: staging pow2=$SOTC_STAGING_LARGE_POW2 cap=$SOTC_STAGING_LARGE_KEEP_MB MiB async upload >=$SOTC_BUF_ASYNC_KB KiB"
echo "SotC GPU work: fill_hle_gpu=$SOTC_FILL_HLE_GPU async_texture_kib=$SOTC_TEX_ASYNC_KB"
echo "SotC forest CPU: compute_prefetch=$SOTC_COMPUTE_PREFETCH vma_gap_cache=$SOTC_VM_GAP_CACHE"
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
# Async graphics pipeline build: previously selected ON and now fixed. The PC renderer may
# temporarily skip >6-index draws whose pipeline is still compiling; this
# can cause temporary missing objects/pop-in on first compile.
# Translation and boot preload stay synchronous to isolate this one change.
export SOTC_ASYNC_SHADERS=1
export SOTC_ASYNC_TRANSLATE=0
export SOTC_ASYNC_PRELOAD=0
# Separate compute deferral. With recording thread + graphics workers this
# would otherwise default ON; both now remain enabled.
export SOTC_ASYNC_COMPUTE=1
# Safe AHB fullscreen transfer optimization; defaults ON only when the blit
# overwrites the entire output surface; letterbox retains clear+barrier.
export SOTC_PRESENT_FULL_BLIT=1
echo "SotC Vulkan compute async=$SOTC_ASYNC_COMPUTE present fullscreen blit=$SOTC_PRESENT_FULL_BLIT"
echo "SotC active graphics pipeline workers: $SOTC_ASYNC_SHADERS (1 may cause temporary missing geometry)"
# Native A/B for stale descriptor reuse vs Vulkan command recording.
# Keep Wave32, TAA, texture LOD, shaders and readbacks unchanged.
# Android host Vulkan command-state memoization only; unlike SOTC_FAST_BIND
# these do not skip guest resource/buffer/texture tracking.
# Set any one to 0 for a reversible comparison without losing the good Turnip.
export SOTC_PIPELINE_BIND_MEMO=1
export SOTC_VERTEX_INPUT_MEMO=1
export SOTC_DESCRIPTOR_SLOT_REUSE=1
echo "SotC host Vulkan fastpaths: pipeline=$SOTC_PIPELINE_BIND_MEMO vertex=$SOTC_VERTEX_INPUT_MEMO descriptor_slots=$SOTC_DESCRIPTOR_SLOT_REUSE"
# Real CPU bottleneck optimization. The CP still refreshes flattened SRTs
# from live guest memory, validates exact shader specialization inputs and
# chooses the same module; draw receives an exact per-op snapshot via swap.
# OFF restores the 0.1.27 path with the original full data copies.
export SOTC_STAGE_SPEC_MEMO=1
export SOTC_STAGE_SNAPSHOT_SWAP=1
export SOTC_REG_SNAPSHOT_MEMO=1
# The verified user profile uses the conservative render-target memo.
export SOTC_RT_MEMO=1
# Native Bionic guest-memory region cache (64 writes journal, 512 direct slots).
# 0 restores generation-only eight-entry cache and all old lock checks.
export SOTC_VM_RANGE_CACHE=1
case "$SOTC_VM_RANGE_CACHE" in
  0|1) ;;
  *) echo "Invalid SOTC_VM_RANGE_CACHE (expected 0/1)" >&2; exit 2 ;;
esac
echo "SotC CPU hot path: shader_spec_exact=$SOTC_STAGE_SPEC_MEMO stage_snapshot_swap=$SOTC_STAGE_SNAPSHOT_SWAP reg_snapshot_memo=$SOTC_REG_SNAPSHOT_MEMO"
echo "SotC Bionic VM: interval cache=$SOTC_VM_RANGE_CACHE; reserve logging capped to 16 (BB_MEMORY_LOG=1 overrides)"
# Controlled cascade-count experiment; default 5 retains the exact original
# renderer path. Never use an invalid setting to suppress unrelated draws.
export SOTC_SUN_CASCADES="${SOTC_SUN_CASCADES:-5}"
case "$SOTC_SUN_CASCADES" in
  0|1|2|3|5) ;;
  *) echo "SotC sun cascade setting invalid; using original 5" >&2
     export SOTC_SUN_CASCADES=5 ;;
esac
# The 0-cascade A/B must stop sun shadow generation at the GAME engine,
# not only clear a Vulkan depth target after PM4 was already produced.
# Verified in Lucas-blip-png/ShadowOfTheColossus-PC launcher:
# fx_sunshadows off -> r_enableCascadeShadows=0 (2026-10-08 A/B).
# This changes a startup CVar, not the AOT compiled guest instructions.
if [ "$SOTC_SUN_CASCADES" = "0" ]; then
    case " ${SOTC_CVARS:-} " in
      *" r_enableCascadeShadows="*) ;;
      *) export SOTC_CVARS="${SOTC_CVARS:+$SOTC_CVARS }r_enableCascadeShadows=0" ;;
    esac
    echo "SotC SUN SHADOW ENGINE OFF: r_enableCascadeShadows=0 requested in SOTC_CVARS"
fi
echo "SotC sun shadow cascade test: $SOTC_SUN_CASCADES (5=original, 0=engine-disabled)"
# A/B performance *diagnostics*, not a performance tweak. The upstream
# stats switches are getenv-presence based: setting either one to "0"
# would STILL activate it. Unset both unless explicitly selected in UI.
if [ "${SOTC_PERF_PROFILE:-0}" = "1" ]; then
    export SOTC_FPS=1
    export SOTC_DRAW_SPLIT=1
    # Native renderer has a bounded scene pass trace: one frame every 300
    # flips. It names the depth target, shadow cascade slice, attachments
    # and number of draw submissions. Never enabled during FPS comparisons.
    export SOTC_PASS_TRACE=1
    unset SOTC_CMD_STATS
    echo "SotC CPU/GPU frame profiling ON: five-second CPU counters + one shadow/pass trace per 300 flips"
else
    # All three source toggles are getenv-presence based, not value based:
    # explicitly unset for ordinary gameplay and unbiased FPS comparisons.
    unset SOTC_FPS SOTC_DRAW_SPLIT SOTC_CMD_STATS SOTC_PASS_TRACE
fi
export SOTC_FAST_BIND=1
export SOTC_RECORD_THREAD=1
echo "SotC fixed engine: fast_bind=$SOTC_FAST_BIND record_thread=$SOTC_RECORD_THREAD rb_async=$SOTC_RB_ASYNC (0=conservative)"
if [ "$SOTC_ASYNC_SHADERS" = "1" ]; then
  echo "SotC pipeline workers: async graphics pipeline build; queued geometry draws can be skipped until ready"
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
export BB_GPU_USER_DIR="$base/gpu-user-srt-phi7-tess-gs-position-turnip-nomultipos-$sotc_gpu_profile/lds-meta1-wave64-fold050"
mkdir -p "$BB_GPU_USER_DIR"
echo "SotC GPU cache revision: srt-phi7-tess-gs-position-turnip-nomultipos; profile=$sotc_gpu_profile; directory=$BB_GPU_USER_DIR"
case ${1:-game} in
    vulkan) exec "$probe" --vulkan-only ;;
    game|compile|verify) ;;
    *) echo "Unknown SotC launcher mode" >&2; exit 2 ;;
esac
sotc_mode=${1:-game}
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
# Non-playing AOT verification. The user never reaches a broken boot or has
# to manually discover that a code library does not match the selected patches.
# A known compiled profile is swapped back in constant time; two previous
# profiles are preserved. Game data and the original eboot are never modified.
if [ "$sotc_mode" = verify ]; then
    select_script="$base/scripts/sotc_aot_select.py"
    if [ -s "$base/user/aot/libSotcAot.so" ] &&
       "$python" "$select_script" --prepared "$out" --report "$base/user/aot/aot-report.json"; then
        echo "SOTC_AOT_VERIFIED: current profile"
        exit 0
    fi
    for candidate in "$base/user/aot-profiles/previous-1" "$base/user/aot-profiles/previous-2"; do
        [ -s "$candidate/libSotcAot.so" ] || continue
        if "$python" "$select_script" --prepared "$out" --report "$candidate/aot-report.json"; then
            swap="$base/user/.aot-swap-$"
            mv "$candidate" "$swap"
            if [ -d "$base/user/aot" ]; then
                mv "$base/user/aot" "$candidate"
            fi
            mv "$swap" "$base/user/aot"
            echo "SOTC_AOT_VERIFIED: reused compiled patch profile"
            exit 0
        fi
    done
    echo "SOTC_AOT_REBUILD_REQUIRED: first access, new game, or changed patch profile"
    exit 6
fi
# Recompile game code on the phone, using the exact same prepared settings.
# The output library is promoted only after a full successful LLVM build and ABI
# validation. Its old working copy remains available on failure.
if [ "$sotc_mode" = compile ]; then
    compiler="${SOTC_AOT_COMPILER_BINARY:-$runtime/aot/bin/libbbrecomp.so}"
    bundle="$runtime/aot/bundle"
    script="$base/scripts/sotc_aot_compile.py"
    [ -x "$compiler" ] && [ -d "$bundle" ] && [ -s "$script" ] ||
        { echo "AOT compiler tools not included in this APK" >&2; exit 4; }
    # Reject the original bb-recomp 1.3.0: it still generates 10 fatal
    # VLoadVectorMasked / VStoreVectorMasked / VPCMPISTRX trap units for SotC.
    # Only the hash-locked patched compiler may be used in a strict AOT release.
    expected="$runtime/aot/sotc-patched-compiler.sha256"
    [ -s "$expected" ] || {
        echo "SotC AOT: patched compiler manifest missing; refusing unsafe official tool" >&2
        exit 4
    }
    # Android mksh may place here-doc temporary files in /data/local,
    # which is forbidden to ordinary apps regardless of sandbox TMPDIR.
    # Read the compiler ELF/hash using a normal Python script instead.
    "$python" "$base/scripts/sotc_aot_verify_compiler.py" \
        --compiler "$compiler" --manifest "$expected" || exit 4
    echo "SOTC AOT: starting on-device ARM64 rebuild (no TSO, no FEX)"
    "$python" "$script" --game "$game" --prepared "$out" \
        --out "$base/user/aot-work" --compiler "$compiler" \
        --bundle-dir "$bundle" --jobs 2 --shards 128
    [ -s "$base/user/aot-work/aot/libSotcAot.so" ] || exit 5
    [ -s "$base/user/aot-work/native-boot-linked.bin" ] || exit 5
    next="$base/user/.aot-next-$$"
    backup="$base/user/.aot-backup-$$"
    mkdir -p "$next"
    cp "$base/user/aot-work/aot/libSotcAot.so" "$next/libSotcAot.so"
    cp "$base/user/aot-work/native-boot-linked.bin" "$next/boot-native.bin"
    cp "$base/user/aot-work/aot-report.json" "$next/aot-report.json"
    # Verify all three items as a consistent set before publishing them.
    if ! "$python" "$base/scripts/sotc_aot_select.py" \
        --prepared "$out" --report "$next/aot-report.json"; then
        echo "SotC AOT: refused invalid compiled code/image/parameter combination" >&2
        rm -rf "$next"
        exit 5
    fi
    [ ! -d "$base/user/aot" ] || mv "$base/user/aot" "$backup"
    if ! mv "$next" "$base/user/aot"; then
        [ ! -d "$backup" ] || mv "$backup" "$base/user/aot"
        exit 5
    fi
    # Retain the preceding two validated AOT profiles: moving between
    # already-compiled effect settings then needs only preparation + SHA checks.
    # Do not copy large code libraries or silently reuse an unverified one.
    if [ -d "$backup" ]; then
        cache="$base/user/aot-profiles"
        mkdir -p "$cache"
        rm -rf "$cache/previous-2"
        if [ -d "$cache/previous-1" ]; then
            mv "$cache/previous-1" "$cache/previous-2"
        fi
        mv "$backup" "$cache/previous-1"
    fi
    echo "SOTC_AOT_READY: $(wc -c < "$base/user/aot/libSotcAot.so") bytes"
    exit 0
fi
# Select only a locally compiled library whose source and patch fingerprints
# match the prepared image. Never reuse stale code when graphics toggles change.
# Fail closed: the APK's bundled library may use a DIFFERENT resolution,
# FPS, effects, title revision or guest image hash. Never use it implicitly.
# The on-phone compiler ensures that this particular profile matches exactly.
if [ ! -s "$base/user/aot/libSotcAot.so" ] || \
   [ ! -s "$base/user/aot/aot-report.json" ]; then
    echo "SOTC AOT: no verified local code. Use COMPILAR AOT NO CELULAR first." >&2
    exit 6
fi
if ! "$python" "$base/scripts/sotc_aot_select.py" \
    --prepared "$out" --report "$base/user/aot/aot-report.json"; then
    echo "SOTC AOT: game or settings changed. Recompile AOT from the launcher." >&2
    exit 6
fi
export BB_AOT="$base/user/aot/libSotcAot.so"
echo "SOTC AOT: verified local library (matches current game and patches)"
# Execute the exact image compiled into libSotcAot.so: patches and engine
# command line are already included. No post-AOT guest code mutation.
set -- "$probe" "$base/user/aot/boot-native.bin" \
    --content-profile "$out/content.bin" \
    --app0 "$game" --user "$base/user" --timeout "${SOTC_TIMEOUT:-0}"
# --sotc-cmdline edits executable bytes at runtime and would invalidate AOT.
# Keep it disabled until that string is injected before compilation.

echo "SotC Bionic: title from BBPROBE5, driver=$driver, ARM64 AOT NO-FEX NO-TSO"
cd "$base"
exec "$@"
