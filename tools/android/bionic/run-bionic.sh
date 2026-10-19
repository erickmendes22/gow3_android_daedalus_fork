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
[ -f "$GOW3_CONFIG" ] || cp "$base/gow3.default.ini" "$GOW3_CONFIG"
setting() { sed -n "s/^$1=//p" "$GOW3_CONFIG" | tail -n 1; }
chip=$("$runtime/bin/kgsl-chip-id" 2>/dev/null || true)
turnip=${GOW3_BIONIC_DRIVER:-auto}
case "$turnip" in
 auto) case "$chip" in 0x44??????) turnip=gen8 ;; 0x07??????|0x43020[01]00|0x43030b00|0x43050a01|0x43050b00|0x43051401) turnip=adreno7xx ;; *) turnip=system ;; esac ;;
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
    trap 'if [ -n "${update_view:-}" ]; then "$python" "$base/scripts/game_update.py" remove "$update_view" 2>/dev/null || true; fi' EXIT
fi


vulkan_status=ok
"$probe" --vulkan-only || { echo 'Bionic Vulkan driver initialization failed' >&2; exit 4; }
"$runtime/bin/gow3-prepare" "$game" "$out"
# Graphics options, patch selection and the direct memory (DMEM)/VBlank the selected patches need.
# GOW3_DEVICE_MEM_MB lets launch_env.py gate the patches by the device's RAM (insufficient-memory-budget).
mem_kb=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || true)
[ -n "$mem_kb" ] && [ "$mem_kb" -gt 0 ] && export GOW3_DEVICE_MEM_MB=${GOW3_DEVICE_MEM_MB:-$((mem_kb/1024))}
# Select game rendering resolution directly.
export GOW3_ANDROID_PORT=1
# Upstream in-process bloodframe is opt-in; settings can update this file live.
export GOW3_LSFG_STATE_FILE="$base/framegen.state"
export GOW3_LSFG_LIB="$runtime/lib/libbloodframe.so"
export GOW3_LSFG_DLL="$base/Lossless.dll"
export GOW3_GAME_DIR="$game"
unset GOW3_ANDROID_FSR_FIXED_OUTPUT GOW3_RENDER_RES GOW3_PATCH_INPUT_RES
export GOW3_UPSCALER=none
export GOW3_FSR1=0
export GOW3_RCAS=0
eval "$("$python" "$base/scripts/launch_env.py" --game "$game" --config "$GOW3_CONFIG" --state "$out/graphics_state.json" --shell)"
# Report what will actually be patched into the verified CUSA01715 eboot, not
# merely the preset selected by the UI. scripts/patches.py checks the signature
# and original bytes again before writing patches.bin.
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
