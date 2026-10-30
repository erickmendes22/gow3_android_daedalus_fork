#!/system/bin/sh
# SotC Bionic/FEX launcher, separate from the God of War III launcher.
set -eu
files=${FXD_FILES:?FXD_FILES is required}
base="$files/gow3port"
runtime="$base/arm64"
python="$runtime/python/bin/python3.13"
probe="$runtime/bin/gow3-probe"
game=${SOTC_GAME_DIR:-${GOW3_GAME_DIR:-$base/game}}
out="$base/sotc-out"
upstream="$base/scripts/sotc-upstream"
prepare="$base/scripts/sotc_prepare_game.py"
[ -x "$probe" ] || { echo "SotC Bionic native loader missing" >&2; exit 2; }
[ -f "$runtime/lib/libbbgpu.so" ] || { echo "SotC Vulkan library libbbgpu.so missing" >&2; exit 2; }
[ -x "$python" ] && [ -f "$prepare" ] && [ -f "$upstream/scripts/prepare.py" ] ||
    { echo "SotC game preparation scripts missing" >&2; exit 2; }
[ -f "$game/eboot.bin" ] && [ -f "$game/sce_sys/param.sfo" ] ||
    { echo "SotC dump requires eboot.bin and sce_sys/param.sfo" >&2; exit 2; }

export HOME="$files/home/gow3port" TMPDIR="$base/tmp" XDG_RUNTIME_DIR="$base/tmp"
export PATH=/system/bin LD_LIBRARY_PATH="$runtime/lib:$runtime/python/lib"
export PYTHONHOME="$runtime/python" PYTHONPATH="$base/scripts" PYTHONUTF8=1
export FEX_APP_CONFIG_LOCATION="$HOME/.fex-emu/"
export FEX_APP_DATA_LOCATION="$HOME/.fex-emu/"
export FEX_APP_CACHE_LOCATION="$HOME/.cache/fex-emu/"
mkdir -p "$TMPDIR" "$HOME/.fex-emu" "$HOME/.cache/fex-emu" "$base/user" "$base/logs" "$out"

chip=$("$runtime/bin/kgsl-chip-id" 2>/dev/null || true)
driver=${GOW3_BIONIC_DRIVER:-auto}
case "$driver" in
  auto)
    case "$chip" in
      0x44??????) driver=gen8 ;;
      0x07??????|0x43020[01]00|0x43030b00|0x43050a01|0x43050b00|0x43051401)
        driver=adreno7xx ;;
      *) driver=system ;;
    esac ;;
  gen8|adreno7xx|system|custom) ;;
  *) echo "Invalid SotC Vulkan driver" >&2; exit 2 ;;
esac
if [ "$driver" = gen8 ] || [ "$driver" = adreno7xx ]; then
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

export GOW3_ANDROID_INPUT=1 GOW3_PAD_FILE="$base/android-pad.state"
export GOW3_PAD_QUIET=1 GOW3_IME_FILE="$base/ime.request"
export GOW3_AUDIO_FIFO="$base/audio.fifo"
export GOW3_PRESENT_SOCKET="$base/present.sock"
export SOTC_PRESENT_SOCKET="$GOW3_PRESENT_SOCKET"
export SOTC_SCREEN_W=${SOTC_SCREEN_W:-1280} SOTC_SCREEN_H=${SOTC_SCREEN_H:-720}
export SOTC_VSYNC=${SOTC_VSYNC:-${GOW3_VSYNC:-1}}
case ${1:-game} in
    vulkan) exec "$probe" --vulkan-only ;;
    game) ;;
    *) echo "Unknown SotC launcher mode" >&2; exit 2 ;;
esac
set -- "$python" "$prepare" --upstream "$upstream" --game-dir "$game" \
    --out "$out" --render "${SOTC_RENDER:-1280x720}" --modes "${SOTC_MODES:-fps60game}"
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
