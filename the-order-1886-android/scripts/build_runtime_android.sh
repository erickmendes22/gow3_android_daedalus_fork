#!/usr/bin/env bash
# The Order 1886 ARM64/Bionic native runtime link (source only; no proprietary game data).
# Usage: GOW3_NDK=/.../ndk/29.0.14206865 bash build_runtime_android.sh order-android out/order1886
set -Eeuo pipefail
source_tree=${1:?Expected assembled The Order source directory}
build_root=${2:-out/order1886}
ndk=${GOW3_NDK:-${ANDROID_NDK_HOME:-}}
: "${ndk:?Set GOW3_NDK to Android NDK r29}"
test -f "$source_tree/src/probe.c"
test -f "$source_tree/src/runtime_pad_bionic.c"
test -f "$source_tree/gpu/shim/order1886_present_client.cpp"
api=${ORDER1886_ANDROID_API:-30}
llvm=$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin
cc="$llvm/aarch64-linux-android${api}-clang"
ar="$llvm/llvm-ar"
prefix=${ORDER1886_BIONIC_PREFIX:-$PWD/.local-deps/android/bionic-prefix}
mkdir -p "$build_root/runtime-objects" "$build_root/atrac9" "$build_root/bin" "$build_root/lib"
test -f "$build_root/gpu/libps4gpu.so" || { echo "Build ps4gpu first" >&2; exit 2; }
test -f "$build_root/fex/liborder1886cpu.so" || { echo "Build order1886cpu first" >&2; exit 2; }
for source in "$source_tree"/third_party/LibAtrac9/C/src/*.c; do
  "$cc" -std=c99 -O2 -g -w -fPIC -c "$source" -o "$build_root/atrac9/$(basename "${source%.c}").o"
done
"$ar" rcs "$build_root/libatrac9.a" "$build_root"/atrac9/*.o
objects=()
for source in "$source_tree"/src/probe.c "$source_tree"/src/runtime*.c "$source_tree"/src/vulkan_smoke.c; do
  obj="$build_root/runtime-objects/$(basename "${source%.c}").o"
  "$cc" -std=gnu11 -O2 -g -Wall -Wextra -Werror -pthread -fPIE \
    -I"$prefix/include" -I"$source_tree" -I"$source_tree/src" \
    -c "$source" -o "$obj"
  objects+=("$obj")
done
cp "$build_root/gpu/libps4gpu.so" "$build_root/lib/"
cp "$build_root/fex/liborder1886cpu.so" "$build_root/lib/"
cp "$llvm/../sysroot/usr/lib/aarch64-linux-android/libc++_shared.so" "$build_root/lib/"
"$cc" "${objects[@]}" "$build_root/libatrac9.a" \
  "$prefix/lib/libavformat.a" "$prefix/lib/libavcodec.a" \
  "$prefix/lib/libswscale.a" "$prefix/lib/libswresample.a" "$prefix/lib/libavutil.a" \
  -L"$build_root/lib" -lps4gpu -lorder1886cpu -lc++_shared \
  -lm -lz -ldl -llog -pthread \
  -Wl,--exclude-libs,libavcodec.a:libavformat.a:libavutil.a:libswscale.a:libswresample.a \
  -rdynamic -pie -Wl,-rpath,'$ORIGIN/../lib' -o "$build_root/bin/order1886-probe"
"$cc" -std=gnu11 -O2 -g -fPIC -shared \
  -I"$source_tree/tools/android/present" -I"$source_tree/tools/android/bionic/present" \
  "$source_tree/tools/android/bionic/present/order1886present.c" \
  -lnativewindow -landroid -llog -ldl -o "$build_root/lib/liborder1886present.so"
"$llvm/llvm-readelf" -h "$build_root/bin/order1886-probe"
echo "Built The Order native ARM64 runtime (not an APK, no gameplay claim)"
