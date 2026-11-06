#!/system/bin/sh
# Experimental Android/Bionic runtime. No Debian, X server or Linux loader.
set -eu
files=${FXD_FILES:?FXD_FILES must identify the app private files directory}
base="$files/gow3port"
runtime="$base/arm64"
python="$runtime/python/bin/python3.13"
export HOME="$files/home/gow3port" TMPDIR="$base/tmp" XDG_RUNTIME_DIR="$base/tmp"
export PATH=/system/bin
export LD_LIBRARY_PATH="$runtime/lib:$runtime/python/lib"
export PYTHONHOME="$runtime/python" PYTHONPATH="$base/scripts" PYTHONUTF8=1
export FEX_APP_CONFIG_LOCATION="$HOME/.fex-emu/" FEX_APP_DATA_LOCATION="$HOME/.fex-emu/" FEX_APP_CACHE_LOCATION="$HOME/.cache/fex-emu/"
export GOW3_BIONIC_RUNNER="$base/run-bionic.sh"
export GOW3_CONFIG="$base/gow3.ini"
mkdir -p "$TMPDIR" "$HOME/.fex-emu" "$HOME/.cache/fex-emu" "$base/user" "$base/logs"
# The in-game capture menu writes this trigger. The renderer dumps 6 actual
# consecutive GSR2 VideoOut dispatches (raw scene/depth/motion/output) here.
export GOW3_DUMP_DIR="$base/out/gsr2-capture"
export GOW3_DUMP_TRIGGER="$base/gsr2-capture.trigger"
# Separate one-flip per-draw framebuffer probe, enabled only by the menu action.
export GOW3_GSR2_STAGE_TRIGGER="$base/gsr2-stages.trigger"
export GOW3_DUMP_FRAMES=6
mkdir -p "$GOW3_DUMP_DIR"
[ -f "$GOW3_CONFIG" ] || cp "$base/gow3.default.ini" "$GOW3_CONFIG"
setting() { sed -n "s/^$1=//p" "$GOW3_CONFIG" | tail -n 1; }
chip=$("$runtime/bin/kgsl-chip-id" 2>/dev/null || true)
turnip=${GOW3_BIONIC_DRIVER:-auto}
case "$turnip" in
 auto) case "$chip" in 0x44??????) turnip=gen8 ;; 0x06??????|0x07??????|0x43020[01]00|0x43030b00|0x43050a01|0x43050b00|0x43051401) turnip=adreno7xx ;; *) turnip=system ;; esac ;;
 gen8|adreno7xx|system|custom) ;;
 *) echo "Invalid Bionic driver selection: $turnip" >&2; exit 2 ;;
esac
unset VK_DRIVER_FILES VK_ICD_FILENAMES VK_LAYER_PATH GOW3_LSFG LSFG_CONFIG GOW3_LSFG_STATE_FILE GOW3_LSFG_LIB
if [ "$turnip" = gen8 ] || [ "$turnip" = adreno7xx ]; then
 export GOW3_VULKAN_DRIVER="$runtime/drivers/$turnip/libvulkan_freedreno.so"
 [ -f "$GOW3_VULKAN_DRIVER" ] || { echo "Bundled $turnip driver is missing" >&2; exit 2; }
elif [ "$turnip" = custom ]; then
 custom=${GOW3_CUSTOM_VULKAN_DRIVER:-}
 case "$custom" in "$files"/gpu-drivers/*/*.so) ;; *) echo 'Invalid custom driver path' >&2; exit 2 ;; esac
 [ -f "$custom" ] || { echo 'Selected custom driver is missing; select a driver on Home' >&2; exit 2; }
 export GOW3_VULKAN_DRIVER="$custom"
 # Companion libraries supplied in the package resolve beside the selected driver.
 export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:${custom%/*}"
else unset GOW3_VULKAN_DRIVER; fi
echo "Bionic Vulkan selection: $turnip${GOW3_VULKAN_DRIVER:+ ($GOW3_VULKAN_DRIVER)}"
export GOW3_ANDROID_INPUT=1 GOW3_PAD_FILE="$base/android-pad.state" GOW3_PAD_QUIET=1
export GOW3_IME_FILE="$base/ime.request" GOW3_AUDIO_FIFO="$base/audio.fifo"
export GOW3_PRESENT_SOCKET="$base/present.sock"
export GOW3_READBACK_LINEAR=1
export GOW3_COPY_GPU_BUFFERS=1
probe="$runtime/bin/gow3-probe"
case ${1:-game} in vulkan) exec "$probe" --vulkan-only ;; esac
out="$base/out"
mkdir -p "$out"
# GOW3_GAME_DIR: the game's folder (eboot.bin, sce_module, sce_sys). Default: gow3port/game.
game=${GOW3_GAME_DIR:-$base/game}
[ -f "$game/eboot.bin" ] || { echo "Game missing: $game (no eboot.bin)" >&2; exit 2; }
echo "Game selection: base=$game update=${GOW3_PATCH_DIR:-none} (update optional)"

# GOW3_PATCH_DIR: an update folder (eboot.bin, sce_sys) laid over the game at start. The merged
# read-only view (scripts/game_update.py) is what prepare/patches/probe use; both dumps stay intact.
update_view=
if [ -n "${GOW3_PATCH_DIR:-}" ]; then
    [ -f "$GOW3_PATCH_DIR/eboot.bin" ] || { echo "Update missing: $GOW3_PATCH_DIR (no eboot.bin)" >&2; exit 2; }
    if ! update_view=$("$python" "$base/scripts/game_update.py" view "$game" "$GOW3_PATCH_DIR" "$out"); then
        echo "Game update: cannot combine the game and its update (see above)" >&2
        exit 2
    fi
    game=$update_view
    echo "Game and update combined from $GOW3_PATCH_DIR" >&2
    # Shared cleanup trap below also removes the ephemeral mods overlay.
fi


# SpartanPort 2.6.0 file mods: resolve the enabled order into a temporary
# read-only game view. The original eboot/game folder is never modified.
mods_view=
mods_on=$(setting load_mods)
case "$mods_on" in 0) ;; *) mods_on=1 ;; esac
if ! mods_view=$("$python" "$base/scripts/mods.py" "$game" --out "$out" \
        --mods-dir "$base/mods" --config "$base/mods.json" --enabled "$mods_on"); then
    echo 'Mods: selected mods could not be mounted; launch cancelled (game files unchanged)' >&2
    exit 2
fi
case "$mods_view" in
    "$out"/mod-game-*) game=$mods_view ;;
    *) [ -f "$mods_view/eboot.bin" ] || { echo "Mods: invalid game view $mods_view" >&2; exit 2; }
       game=$mods_view ;;
esac
trap '
    case "${mods_view:-}" in "$out"/mod-game-*) rm -rf -- "$mods_view" ;; esac
    if [ -n "${update_view:-}" ]; then "$python" "$base/scripts/game_update.py" remove "$update_view" 2>/dev/null || true; fi
' EXIT
echo "Mods: load_mods=$mods_on game_view=$game"
vulkan_status=ok
"$probe" --vulkan-only || { echo 'Bionic Vulkan driver initialization failed' >&2; exit 4; }
"$runtime/bin/gow3-prepare" "$game" "$out"
# Graphics options, patch selection and the direct memory (DMEM)/VBlank the selected patches need.
# GOW3_DEVICE_MEM_MB lets launch_env.py gate the patches by the device's RAM (insufficient-memory-budget).
mem_kb=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || true)
[ -n "$mem_kb" ] && [ "$mem_kb" -gt 0 ] && export GOW3_DEVICE_MEM_MB=${GOW3_DEVICE_MEM_MB:-$((mem_kb/1024))}
# Select game rendering resolution directly.
export GOW3_ANDROID_PORT=1
# R7 forensic probe: one 32x18 RGB readback per GSR2 Vulkan stage, written
# into android-game.log. No image substitution and no framegen/HUD changes.
# No recurring GPU forensic probe in the stable spatial-only mode.
export GOW3_GSR2_AUTO_PROBE=0
# Experimental R8 correctness: initialize every GSR2 display tile before native UI.
export GOW3_GSR2_PREFILL_DISPLAY=1
# Upstream in-process bloodframe is opt-in; settings can update this file live.
export GOW3_LSFG_STATE_FILE="$base/framegen.state"
export GOW3_LSFG_LIB="$runtime/lib/libbloodframe.so"
export GOW3_LSFG_DLL="$base/Lossless.dll"
export GOW3_GAME_DIR="$game"
# Save dialogs temporarily switch the Android overlay to D-pad/Cross/Circle.
export GOW3_SAVE_DIALOG_ACTIVE_FILE="$base/save-dialog.active"
rm -f "$GOW3_SAVE_DIALOG_ACTIVE_FILE"
unset GOW3_ANDROID_FSR_FIXED_OUTPUT GOW3_RENDER_RES GOW3_PATCH_INPUT_RES
export GOW3_UPSCALER=none
export GOW3_FSR1=0
export GOW3_RCAS=0
eval "$("$python" "$base/scripts/launch_env.py" --game "$game" --config "$GOW3_CONFIG" --state "$out/graphics_state.json" --shell)"
# Do not force the desktop 1080p GSR2 output when the verified game patch uses
# another native target: the temporal targets must match the actual guest frame.
if [ "${GOW3_UPSCALER:-none}" = gsr2 ]; then
    # Temporary user-requested fallback: Qualcomm's current-frame spatial
    # reconstruction only. Never reuse previous frame, never add Halton
    # jitter, and NEVER substitute a forced 720p source/output.
    # The game uses the resolution actually selected in Graphics settings.
    export GOW3_GSR2_SPATIAL_ONLY=1
    export GOW3_GSR2_DIRECT_VIDEOOUT=1
    export GOW3_GSR2_PREHUD_COMPOSITE=0
    unset GOW3_GSR2_INPUT_RES GOW3_GSR2_OUTPUT_RES GOW3_OUTPUT_RES
    echo "GSR2: spatial-only reset=1 jitter=0 input/output=real-guest-videoout"
else
    unset GOW3_GSR2_SPATIAL_ONLY GOW3_GSR2_DIRECT_VIDEOOUT
    unset GOW3_GSR2_PREHUD_COMPOSITE GOW3_OUTPUT_RES
fi
# Mali PanVK safe profile. Do not change Snapdragon, Exynos system Vulkan or
# imported drivers that are not Panfrost. Opt out with GOW3_MALI_SAFE_MODE=0.
case "${GOW3_VULKAN_DRIVER:-}" in
  */libvulkan_panfrost.so)
    if [ "${GOW3_MALI_SAFE_MODE:-1}" != 0 ]; then
      # PanVK's Vulkan AHB import succeeds on G615/G720, but direct GPU
      # presentation can leave a black Android surface. Read the completed
      # game frame into a host buffer and copy into a linear, CPU-writable AHB.
      # Off (0) reverts to the unmodified accelerated path for comparisons.
      export GOW3_MALI_CPU_PRESENT=${GOW3_MALI_CPU_PRESENT:-1}
      # 1080p H.264 YUV420P cinematic decoder: pack directly into the
      # game's NV12 framebuffer instead of allocating an FFmpeg NV12 frame,
      # sws_scale() converting, then memcpy() copying the full picture.
      # Only exact 8bit 4:2:0/even frames take this path. =0 restores swscale.
      export GOW3_VIDEODEC_NV12_DIRECT=${GOW3_VIDEODEC_NV12_DIRECT:-1}
      # AHB transaction geometry in gow3present.c already scales the buffer
      # to the physical SurfaceView. No need to CPU-upscale a verified 540p
      # guest frame to the app's historical 1280x720 AHB. Leave higher
      # resolutions and unverified eboots at their original 1280x720.
      # GOW3_MALI_NATIVE_AHB=0 restores the previous output size.
      export GOW3_MALI_NATIVE_AHB=${GOW3_MALI_NATIVE_AHB:-1}
      if [ "$GOW3_MALI_CPU_PRESENT" = 1 ] &&
         [ "$GOW3_MALI_NATIVE_AHB" = 1 ] &&
         [ "${GOW3_RESOLUTION_STATUS:-}" = verified-direct-game-patch ]; then
        case "${GOW3_PATCH_INPUT_RES:-}" in
          960x540|854x480|752x424|640x360|426x240)
            export GOW3_SCREEN_W="${GOW3_PATCH_INPUT_RES%x*}"
            export GOW3_SCREEN_H="${GOW3_PATCH_INPUT_RES#*x}"
            ;;
        esac
      fi
      # 4 buffers rather than 3 gives the FIFO compositor one spare release
      # while the CPU prepares the next image. GOW3_PRESENT_BUFFERS=3 restores
      # the old setting; keep the user's VSync preference untouched.
      export GOW3_PRESENT_BUFFERS=${GOW3_PRESENT_BUFFERS:-4}
      # Fuse alpha normalization with copying RGBA using ARM64 NEON.
      # Set 0 to compare against the previous memcpy + alpha pass.
      export GOW3_MALI_AHB_FAST_COPY=${GOW3_MALI_AHB_FAST_COPY:-1}
      # Use the verified guest patch size as the CPU-present intermediate
      # while preserving the full Android AHB resolution. 0 restores the
      # previous 1920x1080 source for a controlled compatibility comparison.
      export GOW3_MALI_PRESENT_REDUCE=${GOW3_MALI_PRESENT_REDUCE:-1}
      # Under normal pressure evict clean/stale textures first; postpone
      # costly synchronous dirty-image writebacks until ~90% of the Mali
      # memory budget (critical GC still evicts safely at ~95%).
      export GOW3_MALI_GC_CLEAN_FIRST=${GOW3_MALI_GC_CLEAN_FIRST:-1}
      # Restore stable 85% pressure threshold. 88% was unproven for steady
      # 5 FPS and risks retaining extra memory on a memory-shared GPU.
      # Critical cleanup remains at 95%, and =88 is still available.
      export GOW3_MALI_GC_PRESSURE_PCT=${GOW3_MALI_GC_PRESSURE_PCT:-85}
      # G720 2026-11-06 runtime: GC trigger=70% while usage was only
      # ~78% of budget and below 85% pressure. This caused 701 *routine*
      # image evictions in 24 reports, with zero dirty downloads.
      # Stop evicting healthy reusable images with no memory pressure.
      # =70 reproduces the logged baseline for tester A/B.
      # Pressure remains 85% and critical reclaim remains 95%.
      export GOW3_MALI_GC_TRIGGER_PCT=${GOW3_MALI_GC_TRIGGER_PCT:-85}
      # The source-project 68 vs 53 FPS worker result is NOT a G615/G720
      # measurement. Their 2026-11-04 device logs used zero preparation
      # workers. Restore this known Mali baseline and avoid competing with
      # the game's FEX thread until identical-scene A/B proves otherwise.
      # =4 explicitly opts back into checksummed background preparation.
      export GOW3_PREP_WORKERS=${GOW3_PREP_WORKERS:-0}
      # PM4 coroutine spin fix: when the only guest submit is waiting for a
      # memory label and there is no command ready, let the FEX producer run.
      # Same-CPU native benchmark: 71ms -> 40ms useful-work completion,
      # 35.9ms -> 4.9ms CPU waste. This is tester-only, NOT proven FPS.
      # Set 0 to restore original busy-spin behavior.
      export GOW3_MALI_PM4_IDLE_BACKOFF_US=${GOW3_MALI_PM4_IDLE_BACKOFF_US:-20}
      # No checksum consumer when prep_workers=0; set =1 for the old path.
      export GOW3_PM4_CHECKSUM_ALWAYS=${GOW3_PM4_CHECKSUM_ALWAYS:-0}
      # Dirty bitsets only feed the optional two-stage draw recorder.
      # With direct Vulkan draws, tracking them is unused CPU work.
      # =1 restores old tracking independently of draw workers.
      export GOW3_PM4_DIRTY_ALWAYS=${GOW3_PM4_DIRTY_ALWAYS:-0}
      # The TextureSet memo only accepted precomputed hashes; Android
      # had disabled prep workers, leaving that path inactive on misses.
      # Compute equivalent hashes on the GPU thread only when a worker
      # has not produced them, and still validate generation/backing.
      # =0 disables inline fallbacks without disabling existing worker prep.
      export GOW3_MALI_INLINE_TEXTURE_SETS=${GOW3_MALI_INLINE_TEXTURE_SETS:-1}
      # Reuse only retired identical VkImages after GPU completion; cap 128 MiB
      # and purge before pressure (90% budget). 0 restores vmaCreateImage each time.
      export GOW3_MALI_BC_IMAGE_POOL=${GOW3_MALI_BC_IMAGE_POOL:-1}
       # Separately recycle completed exact-match R32G32B32A32Uint images:
       # 64 MiB/24 entries, independent of the existing BC pool.
       # G720 20261106-192404: 12 RGBA128 exact-image reuses / 320
       # requests, no VMA budget-pressure purge or OOM. Low hit ratio does
       # NOT mean a hit has low value when individual cold allocations
       # reach 780 ms. Do not discard those verified wins without matched
       # pressure/FPS evidence. The 90%-budget guard still releases idle
       # images under real pressure. =0 explicitly disables this pool.
       export GOW3_MALI_RGBA128_IMAGE_POOL=${GOW3_MALI_RGBA128_IMAGE_POOL:-1}
      # Memory-only recycling: on an exact VkImage miss, a completed
      # non-dedicated VMA suballocation may be rebound to a DIFFERENT new
      # VkImage after Vulkan size/alignment/type/dedicated guards. Never
      # reuse the old VkImage, its layout, image view or GPU pixels.
      # Hardware benefit is not measured yet: default remains 0.
      # =1 enables the independently rollbackable PanVK experiment.
      export GOW3_MALI_REBIND_RETIRED_MEMORY=${GOW3_MALI_REBIND_RETIRED_MEMORY:-1}
      # Experimental G720 cold-scene retention: BC 128->192 MiB / 24->48 images,
      # RGBA128 64->96 MiB / 24->48; only *retired exact-matched* VkImages.
      # Actual VMA device-local 90% budget guard still flushes on pressure.
      # Set =0 to restore original quota. Do not override the RGB/BC alias guard.
      export GOW3_MALI_SCENE_IMAGE_RETENTION=${GOW3_MALI_SCENE_IMAGE_RETENTION:-1}
      # Retire only clean, unbound BC<->RGBA aliases when their GPU tick has
      # actually completed; always preserve the layout/format reuse guard.
      # =0 restores the 32-tick lifetime without early retirement.
      export GOW3_MALI_BC_ALIAS_RETIRE=${GOW3_MALI_BC_ALIAS_RETIRE:-1}
      # The G720 log has clean BC3->RGBA128 aliases whose GPU completion
      # tick is already retired. Release those images at the verified tick
      # rather than deferring clean BC handles to an unrelated future tick.
      # =0 preserves the previous deferred-release policy for rollback.
      export GOW3_MALI_EAGER_COMPLETED_RETIRE=${GOW3_MALI_EAGER_COMPLETED_RETIRE:-1}
      # Keep VMA's original heap-block policy by default. A 32 MiB block
      # preference has NOT proved less frame stutter or faster creation on G720
      # and may increase memory calls. Explicit 16/32/64/128/256 opt in.
      export GOW3_MALI_VMA_BLOCK_MIB=${GOW3_MALI_VMA_BLOCK_MIB:-0}
      # Lightweight stage timings ON by default for PanVK CPU-present.
      # Samples one frame in 32, logs one aggregate per ~5 s, no captures.
      # Set 0 to measure baseline without the counters.
      export GOW3_MALI_PERF_STATS=${GOW3_MALI_PERF_STATS:-1}
      # G720 matched driver/960x540: the 2-worker + deep-queue experiment
      # ran ~5 FPS vs ~6 FPS with the old 1-worker/2-submit baseline.
      # This is a paired configuration regression, not a proof that the
      # compiler worker alone caused it. Keep the known baseline; =2 opt in.
      export GOW3_GPU_COMPILER_WORKERS=${GOW3_GPU_COMPILER_WORKERS:-1}
      # Async worker-wait remains opt-in. G720's established warm-cache
      # baseline compiles first-use graphics synchronously on the GPU thread;
      # =1 enables worker compile with strict no-skipped-draw waiting.
      export GOW3_MALI_ASYNC_DRAW_WAIT=${GOW3_MALI_ASYNC_DRAW_WAIT:-0}
      export GOW3_BACKGROUND_WARMUP=${GOW3_BACKGROUND_WARMUP:-1}
      # The measured submit_throttle total was <1 ms over several seconds
      # even with cap=4. Restore the proven cap=2 to avoid changing two
      # variables while verifying parallel GPU draw preparation.
      # =4 remains available to benchmark the queue independently.
      # On the 0c61ef0c G720 capture, queue depth 8 did not reduce
      # submit_throttle (0.07 ms over the 780 ms allocation spike window)
      # and PM4 wall still regressed. Revert to the prior conservative
      # PanVK queue depth of 2; Adreno remains unchanged.
      # =8 explicitly re-enables the parity experiment.
      export GOW3_VK_MAX_IN_FLIGHT=${GOW3_VK_MAX_IN_FLIGHT:-2}
      # Bachata-style pending GPU tick cache; set 0 for old polling behavior.
      export GOW3_MALI_CACHED_PENDING_TICKS=${GOW3_MALI_CACHED_PENDING_TICKS:-1}
      # Avoid a global buffer barrier on unrelated image layout transitions.
      # Buffer tracking survives until RAW/WAR/WAW or the next queue submit.
      # =0 reverts to the previously verified all-in-one barrier path.
      export GOW3_MALI_IMAGE_BARRIER_SPLIT=${GOW3_MALI_IMAGE_BARRIER_SPLIT:-1}
      # Read-after-read same-layout images require no Vulkan barrier.  Preserve
      # all read stage/access scopes and merge contiguous identical image
      # subresource barriers. =0 restores the original barrier path.
      export GOW3_MALI_IMAGE_RAR_ELIDE=${GOW3_MALI_IMAGE_RAR_ELIDE:-1}
      export GOW3_VIDEOOUT_LABEL_RETIRE=1
      # Bachata S4 completes Present() before publishing a guest flip event.
      # Do not acknowledge a Mali guest framebuffer while swap work is queued
      # on a different thread; this could recycle a not-yet-presented image.
      export GOW3_PRESENT_THREAD=0
      export GOW3_FRAMES_AHEAD=1
      export GOW3_DEFERRED_READBACK=0
      export GOW3_STALE_READBACK=0
      # The GoW3-specific partial-height cache shortcut is not in the
      # Bachata renderer. It may alias an earlier target after a layout or
      # sample-count change. Prefer correct full image reconstruction on Mali.
      export GOW3_PARTIAL_HEIGHT_VIEWS=0
      # Pass captures force GPU render-pass breaks and extra readbacks. They are
      # for a controlled diagnostic session, never for ordinary Mali gameplay.
      # Explicit GOW3_MALI_AUTOCAPTURE=1 is still available to the developer.
      # Gameplay now defaults to no forensic capture or trace; explicit flags
      # still enable diagnostics without changing the proven render path.
      export GOW3_MALI_VISUAL_TRACE=${GOW3_MALI_VISUAL_TRACE:-0}
      # Full GPU attachment copies can induce PanVK device loss (G720).
      # CPU/AHB snapshots and image/draw telemetry are also opt-in.
      export GOW3_MALI_AUTOCAPTURE=${GOW3_MALI_AUTOCAPTURE:-0}
      export GOW3_MALI_CPU_SNAPSHOTS=${GOW3_MALI_CPU_SNAPSHOTS:-0}
      export GOW3_MALI_PRESENT_PROBE=${GOW3_MALI_PRESENT_PROBE:-0}
      export GOW3_MALI_PRESENT_TRACE=${GOW3_MALI_PRESENT_TRACE:-0}
      if [ "$GOW3_MALI_AUTOCAPTURE" = 1 ] || [ "$GOW3_MALI_CPU_SNAPSHOTS" = 1 ]; then
        export GOW3_MALI_CAPTURE_DIR="$base/logs/mali-captures"
        export GOW3_CAPTURE_DIR="$GOW3_MALI_CAPTURE_DIR"
        mkdir -p "$GOW3_MALI_CAPTURE_DIR"
        rm -f "$GOW3_MALI_CAPTURE_DIR"/guest_*.bmp "$GOW3_MALI_CAPTURE_DIR"/post_*.bmp \
              "$GOW3_MALI_CAPTURE_DIR"/cpu_*.bmp "$GOW3_MALI_CAPTURE_DIR"/frame_*.txt \
              "$GOW3_MALI_CAPTURE_DIR"/scene_*.bmp "$GOW3_MALI_CAPTURE_DIR"/scene_*_pass.txt \
               "$GOW3_MALI_CAPTURE_DIR"/ahb_*.bmp
        # Grouped printf never asks Android mksh to create a heredoc temp file.
        # Android's default heredoc spool under /data/local is not writable.
        {
          printf '%s\n' 'PanVK stages: GPU image-create -> view-create/reject -> texture-binding -> draw -> VideoOut -> guest/post/cpu -> AHB -> Android IPC.'
          printf '%s\n' 'GOW3_MALI_VISUAL records sampled events keyed by image UID, shader hash, flip and AHB buffer; summaries are cumulative, not proof of pixel correctness.'
          printf '%s\n' 'scene_????_3d_colorN.bmp = REAL Vulkan render-target contents after selected 3D draws.'
          printf '%s\n' 'scene_????_3d_depth.bmp = REAL Vulkan depth attachment, grayscale; scene_????_color is first non-depth pass.'
          printf '%s\n' 'scene_????_3d_stencil.bmp = stencil aspect as grayscale where available.'
          printf '%s\n' 'scene_*_pass.txt = pass shader hashes, buffer addresses, physical formats and skip/failure reasons.'
          printf '%s\n' 'ahb_*.bmp = final CPU-writable AHardwareBuffer after scaling/letterboxing and alpha normalization.'
          printf '%s\n' 'frame_*.txt = scene passes, depth, samples and shader hashes; not a scene screenshot.'
          printf '%s\n' 'Previews: accepted guest frames 1 4 12 32 120 360 480 720 and first nonblack transition.'
          printf '%s\n' 'Previews at most 960x540 BMP; stage metadata and MALI_VIDEOOUT_SKIP recorded in android-game.log.'
        } > "$GOW3_MALI_CAPTURE_DIR/README.txt"
      fi
      echo "PanVK Mali safety: compile=$GOW3_GPU_COMPILER_WORKERS async_worker_wait=$GOW3_MALI_ASYNC_DRAW_WAIT warmup=$([ "$GOW3_BACKGROUND_WARMUP" = 0 ] && echo off || echo safe) gpu_submits=$GOW3_VK_MAX_IN_FLIGHT pending_tick_cache=$GOW3_MALI_CACHED_PENDING_TICKS image_barrier_split=$GOW3_MALI_IMAGE_BARRIER_SPLIT image_rar_elide=$GOW3_MALI_IMAGE_RAR_ELIDE frames_ahead=1 deferred=off stale=off partial_views=off capture=$GOW3_MALI_AUTOCAPTURE cpu_snapshots=$GOW3_MALI_CPU_SNAPSHOTS trace=$GOW3_MALI_VISUAL_TRACE probe=$GOW3_MALI_PRESENT_PROBE app_trace=$GOW3_MALI_PRESENT_TRACE present_reduce=$GOW3_MALI_PRESENT_REDUCE gc_clean_first=$GOW3_MALI_GC_CLEAN_FIRST gc_pressure_pct=$GOW3_MALI_GC_PRESSURE_PCT gc_trigger_pct=$GOW3_MALI_GC_TRIGGER_PCT prep_workers=$GOW3_PREP_WORKERS pm4_checksum_always=$GOW3_PM4_CHECKSUM_ALWAYS pm4_dirty_always=$GOW3_PM4_DIRTY_ALWAYS pm4_idle_us=$GOW3_MALI_PM4_IDLE_BACKOFF_US inline_texture_sets=$GOW3_MALI_INLINE_TEXTURE_SETS bc_pool=$GOW3_MALI_BC_IMAGE_POOL rgba128_pool=$GOW3_MALI_RGBA128_IMAGE_POOL memory_rebind=$GOW3_MALI_REBIND_RETIRED_MEMORY scene_retention=$GOW3_MALI_SCENE_IMAGE_RETENTION bc_alias_retire=$GOW3_MALI_BC_ALIAS_RETIRE eager_completed_retire=$GOW3_MALI_EAGER_COMPLETED_RETIRE vma_block_mib=$GOW3_MALI_VMA_BLOCK_MIB perf_stats=$GOW3_MALI_PERF_STATS videodec_nv12_direct=$GOW3_VIDEODEC_NV12_DIRECT sampling=1/32 report=5s native_ahb=$GOW3_MALI_NATIVE_AHB ahb_output=${GOW3_SCREEN_W:-0}x${GOW3_SCREEN_H:-0} buffers=$GOW3_PRESENT_BUFFERS fast_copy=$GOW3_MALI_AHB_FAST_COPY"
    fi
    ;;
esac
# End Mali PanVK safe profile.
echo "Bloodframe: state=$GOW3_LSFG_STATE_FILE dll=$([ -s "$GOW3_LSFG_DLL" ] && echo available || echo missing) lib=$([ -s "$GOW3_LSFG_LIB" ] && echo available || echo missing)"

# Report what will actually be patched into the verified CUSA01715 eboot, not
# merely the preset selected by the UI. scripts/patches.py checks the signature
# and original bytes again before writing patches.bin.
# Never silently launch 720p/native after the user explicitly requested beta 8K.
# patches.py then checks every eboot signature and refuses any incomplete patch.
if [ "$(setting render_resolution)" = 8K ]; then
    case ";${GOW3_PATCHES:-};" in *";Resolution Patch - 8K;"*) ;; *)
        echo "8K EXPERIMENTAL: eboot/available RAM not validated; refusing launch" >&2
        exit 3
    esac
fi
echo "GOW3_NATIVE_RESOLUTION: status=${GOW3_RESOLUTION_STATUS:-unknown} patch=${GOW3_PATCH_INPUT_RES:-standard}"
echo "Game language: system_param=${GOW3_LANGUAGE:-1} (1=English, 7=Portuguese, 17=Portuguese-Brazil)"
# The retail pool is 5056 MiB; the resolution/texture patches ask for more (7104+ for the default
# set). On a phone RAM is the binding constraint: lower the patch set / resolution if the app is
# killed. See docs/ANDROID_PORT.md.
export GOW3_DMEM_MB=${GOW3_DMEM_MB:-0}; [ "${GOW3_DMEM_MB:-0}" -ge 5056 ] 2>/dev/null || export GOW3_DMEM_MB=7104
export GOW3_VBLANK_HZ=${GOW3_VBLANK_HZ:-0}; [ "${GOW3_VBLANK_HZ:-0}" -ge 1 ] 2>/dev/null || export GOW3_VBLANK_HZ=60
echo "Texture integrity: title=${GOW3_GAME_TITLE:-unknown} version=${GOW3_GAME_VERSION:-unknown} patch=${GOW3_PATCH_STATUS:-unknown} shadows=${GOW3_SHADOWS_REQUESTED:-unknown}(${GOW3_SHADOWS_STATUS:-unknown}) readback_linear=${GOW3_READBACK_LINEAR:-1}(${GOW3_READBACK_LINEAR_SOURCE:-unknown}) deferred=${GOW3_DEFERRED_READBACK:-unknown} stale=${GOW3_STALE_READBACK:-unknown} dmem=${GOW3_DMEM_MB}MiB vblank=${GOW3_VBLANK_HZ}Hz turnip=${turnip}"
profile_file="$out/texture-profile.json"
profile_supported=false
[ "${GOW3_PATCH_STATUS:-}" = validated ] && profile_supported=true
printf '%s\n' "{\"title_id\":\"${GOW3_GAME_TITLE:-unknown}\",\"app_version\":\"${GOW3_GAME_VERSION:-unknown}\",\"eboot_sha256\":\"${GOW3_EBOOT_SHA256:-unavailable}\",\"supported\":${profile_supported},\"reason\":\"${GOW3_PATCH_STATUS:-unknown}\"}" > "$profile_file"
"$python" "$base/scripts/texture_diagnostics.py" --out "$out/texture_integrity.json" --profile "$profile_file" --turnip "${turnip}" --dmem "${GOW3_DMEM_MB}" --vblank "${GOW3_VBLANK_HZ}" --vulkan-status "${vulkan_status}"
"$python" "$base/scripts/patches.py" --out "$out" --extra "${GOW3_PATCHES:-}" \
    --game-dir "$game" --patches-dir "${GOW3_PATCHES_DIR:-$base/patches}" \
    --patches-config "${GOW3_PATCHES_CONFIG:-$base/patches.json}"


cd "$base"
echo "Bionic: driver=$turnip chip=$chip; starting God of War III"
"$probe" "$out/boot-linked.bin" --content-profile "$out/content.bin" --patches "$out/patches.bin" \
 --app0 "$game" --user "$base/user" --timeout "${GOW3_TIMEOUT:-0}"
