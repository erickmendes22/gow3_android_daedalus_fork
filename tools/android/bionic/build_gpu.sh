#!/usr/bin/env bash
set -Eeuo pipefail
trap 'printf "Bionic GPU build failed at line %s: %s\n" "$LINENO" "$BASH_COMMAND" >&2' ERR
cd -- "$(dirname -- "$0")/../../.."
ndk=${GOW3_NDK:-${ANDROID_NDK_HOME:-}}
: "${ndk:?Set GOW3_NDK or ANDROID_NDK_HOME}"
api=${GOW3_BIONIC_API:-30}
root=$PWD
prefix=$root/.local-deps/android/bionic-prefix
headers=${GOW3_BIONIC_HEADERS:-$root/.local-deps/root/usr}
out=$root/out/bionic
build=${GOW3_BIONIC_GPU_BUILD:-$out/gpu}
atomic=$("$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android$api-clang" -print-file-name=libatomic.a)
[[ -f $atomic ]] || { echo 'NDK ARM64 libatomic.a is missing' >&2; exit 1; }
[[ -f $prefix/.done-ffmpeg-hidden-v1 ]] || { echo 'Build Bionic FFmpeg with hidden ARM64 NEON globals first (build_deps.sh)' >&2; exit 1; }
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH CMAKE_PREFIX_PATH
export PATH="$headers/bin:$PATH"
export PKG_CONFIG_LIBDIR="$prefix/lib/pkgconfig:$prefix/share/pkgconfig"
export PKG_CONFIG_PATH=$PKG_CONFIG_LIBDIR
unset PKG_CONFIG_SYSROOT_DIR
for patch in gpu/patches/fsr-vulkan/*.patch; do
    if ! git -C gpu/third_party/fsr-vulkan apply --reverse --check "$root/$patch" 2>/dev/null; then
        git -C gpu/third_party/fsr-vulkan apply "$root/$patch"
    fi
done
# Let CMake discover include/vma as well as include; discard the old forced cache path.
mkdir -p "$build/.cmake/api/v1/query"
touch "$build/.cmake/api/v1/query/codemodel-v2"
cmake -S gpu -B "$build" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ndk/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM="android-$api" -DANDROID_STL=c++_shared \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo -DGOW3_PGO=off -DGOW3_LTO=OFF \
    -DCMAKE_FIND_ROOT_PATH="$prefix" -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH \
    -DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY -Dpkgcfg_lib_FFMPEG_atomic:FILEPATH="$atomic" \
    -DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=BOTH "-DCMAKE_PREFIX_PATH=$prefix;$headers" \
    -UVMA_INCLUDE_DIR
python3 tools/android/bionic/audit_link.py --build "$build" --prefix "$prefix" --ndk "$ndk"
if [[ ${1:-} == --configure-only ]]; then exit 0; fi
cmake --build "$build" --target gow3gpu --parallel "${GOW3_JOBS:-2}"
mkdir -p "$out/lib"
cp "$build/libgow3gpu.so" "$out/lib/"
