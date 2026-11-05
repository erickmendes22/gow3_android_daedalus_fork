#!/usr/bin/env bash
# Build the complete, game-free ARM64 runtime input chain for the Gow3 Android APK.
set -euo pipefail
cd -- "$(dirname -- "$0")/../../.."
root=$PWD
sysroot=${GOW3_ARM64_SYSROOT:-$root/.local-deps/android/arm64-sysroot}
rootfs=${GOW3_RUNTIME_ROOTFS:-$root/.local-deps/android/migration/x/rootfs}
export GOW3_RUNTIME_ROOTFS=$rootfs
device_libs=${GOW3_DEVICE_LIBS:-$root/out/arm64/device-libs.txt}

die() { echo "build_android_runtime: $*" >&2; exit 1; }
[[ -d $sysroot ]] || die "ARM64 sysroot missing: $sysroot"
[[ -d $rootfs ]] || die "fexdroid migration rootfs missing: $rootfs"
command -v clang >/dev/null || die 'clang is required'
if [[ -z ${GOW3_FEX_SOURCE:-} && -f $root/../Bloodborne-Android/third_party/FEX/CMakeLists.txt ]]; then
    export GOW3_FEX_SOURCE=$root/../Bloodborne-Android/third_party/FEX
fi

# ---- progress helpers -------------------------------------------------------
step=0
total=7
_t0=0

begin() { step=$((step + 1)); _t0=$(date +%s); printf '\n==> [%d/%d] %s\n' "$step" "$total" "$*"; }

end_stage() {
    local sec=$(( $(date +%s) - _t0 ))
    printf '    %s (%dm%02ds)\n' "$*" "$((sec / 60))" "$((sec % 60))"
}

# ---- 1/7 native ARM64 components (CPU + GPU + probe) -------------------------
begin "ARM64 native components (build_arm64.sh)"
bash tools/android/build/build_arm64.sh
end_stage "libgow3cpu.so / libgow3gpu.so / gow3-probe"

# ---- 2/7 device library list + KGSL chip id ---------------------------------
begin "device-libs + kgsl-chip-id"
mkdir -p "$(dirname -- "$device_libs")"
find "$rootfs/usr/lib/aarch64-linux-gnu" -type f -print |
    sed 's|.*/||' | sort -u > "$device_libs"
clang --target=aarch64-linux-gnu --sysroot="$sysroot" -O2 -fuse-ld=lld \
    tools/android/build/kgsl_chip_id.c -o out/arm64/kgsl-chip-id
end_stage "device-libs.txt / kgsl-chip-id"

# ---- 3/7 ARM64 bundle --------------------------------------------------------
begin "ARM64 bundle"
python3 tools/android/build_arm64_bundle.py \
    --device-libs "$device_libs" --sysroot "$sysroot"
end_stage "out/arm64/bundle/"

# ---- 4/7 Turnip main variant ------------------------------------------------
begin "Turnip main"
bash tools/android/build/build_turnip.sh main
end_stage "out/arm64/turnip/"

# ---- 5/7 Turnip gen8 variant (Adreno 8xx) -----------------------------------
begin "Turnip gen8"
bash tools/android/build/build_turnip.sh gen8
end_stage "out/arm64/turnip-gen8/"

# ---- 6/7 LSFG (lossless scaling frame generation) ---------------------------
begin "LSFG (lsfg-vk v1.0.0)"
bash tools/android/build/build_lsfg.sh
end_stage "out/arm64/lsfg/"

# ---- 7/7 release runtime archive --------------------------------------------
begin "Release runtime archive"
python3 tools/android/runtime/build_release_runtime.py
end_stage "out/release/runtime.tar.gz"

printf '\nAndroid runtime ready: %s\n' "$root/out/release/runtime.tar.gz"
