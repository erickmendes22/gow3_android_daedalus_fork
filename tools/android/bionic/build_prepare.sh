#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../../.."
what=${1:-android}
flags=(-std=c++17 -O2 -g -Wall -Wextra -Werror -Wno-unused-parameter)
case "$what" in
  host)
    mkdir -p out/host
    "${CXX:-c++}" "${flags[@]}" tools/android/bionic/prepare/*.cpp -lz -o out/host/gow3-prepare ;;
  android)
    ndk=${GOW3_NDK:-${ANDROID_NDK_HOME:-}}
    : "${ndk:?Set GOW3_NDK or ANDROID_NDK_HOME}"
    api=${GOW3_BIONIC_API:-30}
    llvm=$ndk/toolchains/llvm/prebuilt/linux-x86_64
    mkdir -p out/bionic/bin
    "$llvm/bin/aarch64-linux-android$api-clang++" "${flags[@]}" -static-libstdc++ -pie \
      tools/android/bionic/prepare/*.cpp "$llvm/sysroot/usr/lib/aarch64-linux-android/libz.a" \
      -o out/bionic/bin/gow3-prepare ;;
  *) echo 'usage: build_prepare.sh [host|android]' >&2; exit 2 ;;
esac
