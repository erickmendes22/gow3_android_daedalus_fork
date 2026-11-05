#!/bin/sh
# Launch script for the God of War III port on Android (gow3_android).
#
# Runs inside the app sandbox on top of the fexdroid ARM64 rootfs. The app starts it as:
#   <rootfs>/bin/sh <files>/gow3port/run-gow3.sh game
#
# It is the Android twin of the desktop run.sh: same prepare -> patches -> probe flow, but the
# paths are the app's private directories, Python comes from the rootfs, and the display / input /
# audio / shared-memory bridges are the app's (see the display and input bridge classes).
set -eu
files=${FXD_FILES:-/data/user/0/com.gow3.android/files}
host="$files/rootfs"
base="$files/gow3port"
arch="$base/arm64"
loader="$host/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1"
probe="$arch/bin/gow3-probe"
export FXD_FILES="$files" FXD_ROOT="$host"
export PATH="$host/usr/bin:$host/bin:/system/bin"
export HOME="$files/home/gow3port"
export TMPDIR="$host/tmp" XDG_RUNTIME_DIR="$host/tmp"
# lib/ next to the probe holds libgow3gpu/libgow3cpu and the libraries the rootfs lacks.
export LD_LIBRARY_PATH="$arch/lib:$host/usr/lib/aarch64-linux-gnu:$host/usr/lib/aarch64-linux-gnu/pulseaudio:$host/usr/lib"

# Turnip: Mesa main for Adreno 6xx/7xx, the turnip/gen8 build on Adreno 8xx (0x44..., e.g. the
# 8 Elite's 830). GOW3_TURNIP=main|gen8 overrides the choice.
turnip=${GOW3_TURNIP:-}
if [ -z "$turnip" ]; then
    case $("$loader" "$arch/bin/kgsl-chip-id" 2>/dev/null || true) in
        0x44*) turnip=gen8 ;;
        *) turnip=main ;;
    esac
fi
icd="$host/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json"
[ "$turnip" = gen8 ] && [ -f "$host/usr/share/vulkan/icd.d/freedreno_gen8_icd.aarch64.json" ] &&
    icd="$host/usr/share/vulkan/icd.d/freedreno_gen8_icd.aarch64.json"
echo "Turnip: ${icd##*/}"
export VK_DRIVER_FILES="$icd"
export VK_ICD_FILENAMES="$VK_DRIVER_FILES"
# The guest's x86-64 code runs under FEXCore; its glibc needs the unsupported-instruction tunables
# the desktop uses too.
export GLIBC_TUNABLES='glibc.cpu.hwcaps=-AVX2,-AVX,-AVX_Fast_Unaligned_Load,-AVX2_Usable,-AVX_Usable'

export GOW3_CONFIG="$base/gow3.ini"
[ -f "$GOW3_CONFIG" ] || cp "$base/gow3.default.ini" "$GOW3_CONFIG"
# One setting from gow3.ini, last value wins (the launcher writes whole-file on changes).
setting() { sed -n "s/^$1=//p" "$GOW3_CONFIG" 2>/dev/null | tail -n 1; }

# Bridges the app provides (it sets GOW3_ANDROID_INPUT=1 when they are up).
if [ "${GOW3_ANDROID_INPUT:-0}" = 1 ]; then
    export GOW3_PAD_FILE="$base/android-pad.state" GOW3_PAD_QUIET=1
    # Text the game asks for (the character name): the app's touch keyboard.
    export GOW3_IME_FILE="$base/ime.request"
    # Sound: SDL's disk driver mixes into the FIFO the app plays. Only when the app made it: a
    # FIFO nobody reads would stall the game's audio. Its reads pace the output.
    if [ -p "$base/audio.fifo" ] && [ -f "$base/audio.fifo.ready" ]; then
        export SDL_AUDIO_DRIVER=disk SDL_AUDIO_DISK_OUTPUT_FILE="$base/audio.fifo"
        export SDL_AUDIO_DISK_TIMESCALE=0 SDL_AUDIO_DEVICE_SAMPLE_FRAMES=512
    else
        echo "Android audio bridge is not ready (expected $base/audio.fifo.ready)" >&2
        exit 12
    fi
fi

export SDL_VIDEODRIVER=x11 DISPLAY=:0
export MESA_VK_WSI_DEBUG=sw MESA_VK_WSI_PRESENT_MODE=relaxed
# The display bridge hands frames over directly through this socket (the ordinary X11 path can
# show black on Android).
export FEXDROID_PRESENT="$host/tmp/fxpresent.sock"
export SDL_JOYSTICK_HIDAPI=0
export SDL_GAMECONTROLLERCONFIG_FILE="$base/gow3-gamecontrollerdb.txt"
export PULSE_SERVER="unix:$host/tmp/pulse/native" PULSE_LATENCY_MSEC=60

python="$host/usr/bin/python3.13"
[ -x "$loader" ] || { echo "No rootfs loader in the runtime" >&2; exit 2; }
[ -x "$python" ] || { echo "No Python in the runtime; cannot prepare the game files" >&2; exit 2; }
out="$base/out"
mkdir -p "$out" "$base/user"
export PYTHONPATH="$base/scripts"

case ${1:-game} in
    vulkan)
        # GPU check without the game (needs the app's display bridge / a Vulkan device).
        exec "$loader" "$probe" --vulkan-only
        ;;
    cpu|check)
        # Offline checks on an already prepared image: no GPU involved.
        [ -f "$out/boot-linked.bin" ] || { echo "Prepare the game first (run 'game')." >&2; exit 2; }
        game=${GOW3_GAME_DIR:-$base/game}
        if [ "$1" = cpu ]; then exec "$loader" "$probe" "$out/boot-linked.bin" --cpu-only --app0 "$game"; fi
        exec "$loader" "$probe" "$out/boot-linked.bin" --app0 "$game" --check-imports
        ;;
esac

# GOW3_GAME_DIR: the game's folder (eboot.bin, sce_module, sce_sys). Default: gow3port/game.
game=${GOW3_GAME_DIR:-$base/game}
[ -f "$game/eboot.bin" ] || { echo "Game missing: $game (no eboot.bin)" >&2; exit 2; }

# GOW3_PATCH_DIR: an update folder (eboot.bin, sce_sys) laid over the game at start. The merged
# read-only view (scripts/game_update.py) is what prepare/patches/probe use; both dumps stay intact.
update_view=
if [ -n "${GOW3_PATCH_DIR:-}" ]; then
    [ -f "$GOW3_PATCH_DIR/eboot.bin" ] || { echo "Update missing: $GOW3_PATCH_DIR (no eboot.bin)" >&2; exit 2; }
    if ! update_view=$(PYTHONHOME="$host/usr" "$loader" "$python" "$base/scripts/game_update.py" view "$game" "$GOW3_PATCH_DIR" "$out"); then
        echo "Game update: cannot combine the game and its update (see above)" >&2
        exit 2
    fi
    game=$update_view
    echo "Game and update combined from $GOW3_PATCH_DIR" >&2
    trap 'if [ -n "${update_view:-}" ]; then PYTHONHOME="$host/usr" "$loader" "$python" "$base/scripts/game_update.py" remove "$update_view" 2>/dev/null || true; fi' EXIT
fi

# A reproducible capture: the tester names it (GOW3_CAPTURE_ID) and the display-boundary marker
# is written outside the repository/APK so frame captures can be matched to a run without ever
# bundling game content. The launcher reads this marker to expose the capture directory.
if [ -n "${GOW3_CAPTURE_ID:-}" ]; then
    capture_dir=${GOW3_CAPTURE_DIR:-$files/gow3port/captures/$GOW3_CAPTURE_ID}
    export GOW3_CAPTURE_DIR="$capture_dir"
    mkdir -p "$capture_dir"
    echo "Capture marker: $capture_dir (capture_id=$GOW3_CAPTURE_ID)"
fi

# Validate Vulkan/Turnip directly, without frame-generation layers.
vulkan_status=unknown
vulkan_log="$out/.vulkan-check.log"
if "$loader" "$probe" --vulkan-only >"$vulkan_log" 2>&1; then
    vulkan_status=ok
    rm -f "$vulkan_log"
else
    vulkan_status=failed
    echo "Graphics: Vulkan/Turnip initialization FAILED (turnip=${turnip}, icd=${icd##*/}); texture integrity is NOT validated" >&2
    # Surface the last 40 lines of the Vulkan check (typically lsfg-vk's "lsfg-vk: ..." messages
    # or the driver stack) so the player can see what the layer did. We never write the game's
    # own texture assets here; only Vulkan / lsfg-vk / driver output.
    if [ -f "$vulkan_log" ]; then
        echo "Vulkan check output (last 40 lines):" >&2
        tail -n 40 "$vulkan_log" >&2 || true
        mv -f "$vulkan_log" "$out/vulkan-check-last.log"
    fi
fi
export GOW3_VULKAN_STATUS="$vulkan_status"
# A driver failure is fatal: the game cannot present, and the log must say so distinctly. Write a
# diagnostic record first so the failure is part of the evidence, not just an exit code.
if [ "$vulkan_status" != ok ]; then
    mkdir -p "$out"
    printf '%s\n' "{\"title_id\":\"${GOW3_GAME_TITLE:-unknown}\",\"app_version\":\"${GOW3_GAME_VERSION:-unknown}\",\"eboot_sha256\":\"${GOW3_EBOOT_SHA256:-unavailable}\",\"supported\":false,\"reason\":\"${GOW3_PATCH_STATUS:-unknown}\",\"vulkan_status\":\"failed\"}" > "$out/texture_integrity.json"
    echo "Graphics: aborting launch; see the runtime log for the driver error (log: $base/logs/android-game.log)" >&2
    exit 4
fi

# Prepare the runtime image from the player's own files (cached: prepare.py checks the sources).
PYTHONHOME="$host/usr" "$loader" "$python" "$base/scripts/prepare.py" "$game" --out "$out"
PYTHONHOME="$host/usr" "$loader" "$python" "$base/scripts/link_libc.py" "$game" --out "$out"
PYTHONHOME="$host/usr" "$loader" "$python" "$base/scripts/link_modules.py" "$game" --out "$out"
PYTHONHOME="$host/usr" "$loader" "$python" "$base/scripts/content_profile.py" "$game" --out "$out" --sku "${GOW3_CONTENT_SKU:-full}"
# Graphics options, patch selection and the direct memory (DMEM)/VBlank the selected patches need.
# GOW3_DEVICE_MEM_MB lets launch_env.py gate the patches by the device's RAM (insufficient-memory-budget).
mem_kb=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || true)
[ -n "$mem_kb" ] && [ "$mem_kb" -gt 0 ] && export GOW3_DEVICE_MEM_MB=${GOW3_DEVICE_MEM_MB:-$((mem_kb/1024))}
# Select game rendering resolution directly.
export GOW3_ANDROID_PORT=1
unset GOW3_ANDROID_FSR_FIXED_OUTPUT GOW3_RENDER_RES GOW3_PATCH_INPUT_RES
export GOW3_UPSCALER=none
export GOW3_FSR1=0
export GOW3_RCAS=0
eval "$(PYTHONHOME="$host/usr" "$loader" "$python" "$base/scripts/launch_env.py" --game "$game" --config "$GOW3_CONFIG" --state "$out/graphics_state.json" --shell)"
# Report what will actually be patched into the verified CUSA01715 eboot, not
# merely the preset selected by the UI. scripts/patches.py checks the signature
# and original bytes again before writing patches.bin.
echo "GOW3_NATIVE_RESOLUTION: status=${GOW3_RESOLUTION_STATUS:-unknown} patch=${GOW3_PATCH_INPUT_RES:-standard}"
echo "Game language: system_param=${GOW3_LANGUAGE:-1} (1=English, 17=Portuguese-Brazil)"
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
PYTHONHOME="$host/usr" "$loader" "$python" "$base/scripts/texture_diagnostics.py" --out "$out/texture_integrity.json" --profile "$profile_file" --turnip "${turnip}" --dmem "${GOW3_DMEM_MB}" --vblank "${GOW3_VBLANK_HZ}" --vulkan-status "${vulkan_status}"
PYTHONHOME="$host/usr" "$loader" "$python" "$base/scripts/patches.py" --out "$out" --extra "${GOW3_PATCHES:-}" \
    --game-dir "$game" --patches-dir "${GOW3_PATCHES_DIR:-$base/patches}" \
    --patches-config "${GOW3_PATCHES_CONFIG:-$base/patches.json}"

cd "$base"
echo "God of War III: starting (DMEM ${GOW3_DMEM_MB} MiB, vblank ${GOW3_VBLANK_HZ} Hz)"
rc=0
"$loader" "$probe" "$out/boot-linked.bin" \
    --content-profile "$out/content.bin" --patches "$out/patches.bin" \
    --app0 "$game" --user "$base/user" --timeout "${GOW3_TIMEOUT:-0}" || rc=$?
# When an update view was created, its removal runs in the EXIT trap (the dumps stay untouched).
exit $rc
