#!/usr/bin/env bash
# Compile the experimental Bionic game components. Does not package or switch the APK runtime.
set -Eeuo pipefail
trap 'printf "Bionic runtime build failed at line %s: %s\n" "$LINENO" "$BASH_COMMAND" >&2' ERR
cd -- "$(dirname -- "$0")/../../.."
ndk=${GOW3_NDK:-${ANDROID_NDK_HOME:-}}
: "${ndk:?Set GOW3_NDK or ANDROID_NDK_HOME}"
export GOW3_NDK=$ndk
api=${GOW3_BIONIC_API:-30}
llvm=$ndk/toolchains/llvm/prebuilt/linux-x86_64
out=$PWD/out/bionic
prefix=$PWD/.local-deps/android/bionic-prefix
if [[ ${1:-} != --link-only ]]; then
    bash tools/android/bionic/build_deps.sh
    bash tools/android/bionic/build_gpu.sh --configure-only
    bash tools/android/bionic/build_cpu.sh
    bash tools/android/bionic/build_gpu.sh
fi
mkdir -p "$out/bin" "$out/lib" "$out/runtime-objects" "$out/atrac9"
cc=("$llvm/bin/aarch64-linux-android$api-clang")
for source in third_party/LibAtrac9/C/src/*.c; do
    "${cc[@]}" -std=c99 -O2 -g -w -fPIC -c "$source" -o "$out/atrac9/$(basename "${source%.c}").o"
done
"$llvm/bin/llvm-ar" rcs "$out/libatrac9.a" "$out"/atrac9/*.o
objects=()
for source in src/probe.c src/runtime*.c src/vulkan_smoke.c ports/sotc/android/lowmem.c ports/sotc/android/gpu_bridge.c; do
    obj="$out/runtime-objects/$(basename "${source%.c}").o"
    "${cc[@]}" -std=c11 -O2 -g -Wall -Wextra -Werror -pthread -I"$prefix/include" -I. -Isrc \
        -fPIE -c "$source" -o "$obj"
    objects+=("$obj")
done
"${cc[@]}" "${objects[@]}" "$out/libatrac9.a" \
    "$prefix/lib/libavformat.a" "$prefix/lib/libavcodec.a" "$prefix/lib/libswscale.a" \
    "$prefix/lib/libswresample.a" "$prefix/lib/libavutil.a" -L"$out/lib" -lgow3gpu -lgow3cpu -lc++_shared \
    -lm -ldl -pthread -Wl,--exclude-libs,libavcodec.a:libavformat.a:libavutil.a:libswscale.a:libswresample.a -rdynamic -pie -Wl,-rpath,'$ORIGIN/../lib' -o "$out/bin/gow3-probe"
"${cc[@]}" -std=c11 -O2 -Wall -Wextra -Werror -pie tools/android/build/kgsl_chip_id.c -o "$out/bin/kgsl-chip-id"
"${cc[@]}" -std=c11 -O2 -g -Wall -Wextra -Werror -fPIC -shared -Itools/android/present \
    tools/android/bionic/present/gow3present.c -lnativewindow -landroid -llog -ldl -o "$out/lib/libgow3present.so"
bash tools/android/bionic/build_prepare.sh android
python3 tools/android/bionic/verify_bionic.py --ndk "$ndk" --api "$api" --root "$out"
args=()
if [[ -n ${GOW3_BIONIC_DRIVER_ZIP:-} ]]; then args=(--archive "$GOW3_BIONIC_DRIVER_ZIP"); fi
python3 tools/android/bionic/stage_driver.py "${args[@]}" --output "$out/drivers/gen8"

python3 tools/android/bionic/stage_driver.py --manifest tools/android/bionic/driver-adreno7xx.json --output "$out/drivers/adreno7xx"
