#!/usr/bin/env bash
# Build this fork's pinned FEX and CPU wrapper for Bionic; no Linux loader/rootfs.
set -Eeuo pipefail
trap 'printf "Bionic CPU build failed at line %s: %s\n" "$LINENO" "$BASH_COMMAND" >&2' ERR
cd -- "$(dirname -- "$0")/../../.."
ndk=${GOW3_NDK:-${ANDROID_NDK_HOME:-}}
: "${ndk:?Set GOW3_NDK or ANDROID_NDK_HOME}"
api=${GOW3_BIONIC_API:-30}
out=$PWD/out/bionic
fex=${GOW3_FEX_SOURCE:-$PWD/third_party/FEX}
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH CMAKE_PREFIX_PATH
cmake -S "$fex" -B "$out/fex" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ndk/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM="android-$api" -DANDROID_STL=c++_shared \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_PROJECT_FEX_INCLUDE="$PWD/cpu/fex_project.cmake" \
    -DBUILD_TESTING=OFF -DBUILD_THUNKS=OFF -DBUILD_FEXCONFIG=OFF -DBUILD_STEAM_SUPPORT=OFF \
    -DBUILD_FEX_LINUX_TESTS=OFF -DENABLE_ZYDIS=OFF -DTUNE_ARCH=armv8.2-a -DTUNE_CPU=generic \
    -DENABLE_JEMALLOC_GLIBC_ALLOC=OFF
cmake --build "$out/fex" --target gow3cpu --parallel "${GOW3_JOBS:-2}"
mkdir -p "$out/lib"
cp "$out/fex/libgow3cpu.so" "$out/lib/"
cp "$ndk/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so" "$out/lib/"
