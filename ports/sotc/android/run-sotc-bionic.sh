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
# The working Bachata S4+ SotC profile uses precise GPU readbacks (mode 2).
# The PC SotC renderer also defaults to that mode, but additionally launches
# readbacks asynchronously. Android keeps their completion synchronous to
# avoid stale GPU data at CPU read faults while troubleshooting visual flicker.
# These are scoped to this SotC process; they do not modify GoW3 or Bachata.
export BB_READBACKS=2
export SOTC_RB_ASYNC=0
# Upstream's 32 MiB/frame texture upload budget defers large first-use textures
# and explicitly fills those images with zero texels (black) until a later flip.
# SotC Android prioritizes complete materials over area-transition frame time:
# upload the actual texture before it is sampled, never its zero-fill placeholder.
# 0 is a documented and implemented disable value in texture_cache.cpp.
export SOTC_UPLOAD_BUDGET_MB=0
echo "SotC texture integrity: zero-fill upload deferral disabled"
# Recover dynamic descriptor arrays in material/lighting fragment shaders.
# The vertex shader array path stays excluded (known upstream GPU hang).
export SOTC_ANDROID_FRAGMENT_TSHARP=1
echo "SotC render coherence: precise GPU readbacks, synchronous completion"
# Rendering correctness first on Android: the PC backend can return nullptr
# for geometry draws while asynchronous shaders/pipelines are still being
# compiled (vk_pipeline_cache.cpp). With a cold shader cache this produces
# missing geometry and transient flicker, not merely poor FPS.
# The Android port must never silently drop these draws. Shader compilation
# can stall a frame, but the complete frame will be drawn once compiled.
export SOTC_ASYNC_SHADERS=0
export SOTC_ASYNC_TRANSLATE=0
export SOTC_ASYNC_PRELOAD=0
echo "SotC render completeness: synchronous graphics shaders and pipelines; no async draw skips"
# Fragment barycentric interpolation now selects a capability-gated
# auxiliary GS on Adreno where both native extensions are missing.
# Old shaders have no matching GS inputs and MUST NOT be reused.
# Descriptor-array lowering also covers fragment shaders.
# The IR lowering changed after the early 0.1.4 SRT implementation.
# Pipeline keys do not encode the lowering revision: never reopen old SPIR-V
# or SRT walkers even if the game hash and Vulkan profile match.
# Keep both subgroup variants separate and preserve --user "$base/user" saves.
case "${SOTC_ADRENO_WAVE32:-0}" in
    1) sotc_gpu_profile=wave32 ;;
    *) sotc_gpu_profile=wave64 ;;
esac
export BB_GPU_USER_DIR="$base/gpu-user-srt-phi5-turnip-nomultipos-$sotc_gpu_profile"
mkdir -p "$BB_GPU_USER_DIR"
echo "SotC GPU cache revision: srt-phi5-turnip-nomultipos; profile=$sotc_gpu_profile; directory=$BB_GPU_USER_DIR"
case ${1:-game} in
    vulkan) exec "$probe" --vulkan-only ;;
    game) ;;
    *) echo "Unknown SotC launcher mode" >&2; exit 2 ;;
esac
set -- "$python" "$prepare" --upstream "$upstream" --game-dir "$game" \
    --out "$out" --render "${SOTC_RENDER:-1280x720}" --modes "${SOTC_MODES-fps60game}" \
    --cvars "${SOTC_CVARS:-doIndexBufferCulling=0 doSunShadowIndexBufferCulling=0}"
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
