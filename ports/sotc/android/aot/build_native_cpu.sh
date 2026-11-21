#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Strict ARM64 AOT CPU backend (no FEX or TSO). No game data enters CI.
set -Eeuo pipefail
cd "$(dirname "$0")/../../../.."
root="$PWD"
ndk="$(printenv SOTC_NDK || printenv ANDROID_NDK_HOME || true)"
[[ -n "$ndk" ]] || { echo "Set SOTC_NDK or ANDROID_NDK_HOME to Android NDK r29+" >&2; exit 2; }
api="$(printenv SOTC_ANDROID_API || echo 30)"
llvm="$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin"
cxx="$llvm/aarch64-linux-android$api-clang++"
cc="$llvm/aarch64-linux-android$api-clang"
[[ -x "$cxx" && -x "$cc" ]] || { echo "AArch64 NDK compiler not found" >&2; exit 2; }
readelf="$(printenv READELF || echo readelf)"
command -v "$readelf" >/dev/null

pin=b6d4cfb6972c84d4029f54765406ec143df3c30e
upstream="$(printenv SOTC_AOT_UPSTREAM || echo "$root/.local-deps/Bloodborne-Android-AOT")"
if [[ ! -d "$upstream/.git" ]]; then
  mkdir -p "$upstream"
  git -C "$upstream" init -q
  git -C "$upstream" remote add origin https://github.com/ducvd89/Bloodborne-Android.git
  git -C "$upstream" sparse-checkout init --cone
  git -C "$upstream" sparse-checkout set cpu src/guest_cpu.h
fi
if [[ "$(git -C "$upstream" rev-parse HEAD 2>/dev/null || echo missing)" != "$pin" ]]; then
  git -C "$upstream" fetch --depth=1 origin "$pin"
  git -C "$upstream" checkout --detach -f FETCH_HEAD
fi
[[ "$(git -C "$upstream" rev-parse HEAD)" == "$pin" ]] || { echo "Upstream AOT pin mismatch" >&2; exit 2; }

out="$root/out/sotc-arm64-aot"
src="$out/src"
python3 ports/sotc/android/aot/port_guest_context.py --upstream "$upstream" --out "$src"
mkdir -p "$out"
"$cxx" -std=c++20 -O2 -Wall -Wextra -Werror -fPIC -shared \
  -fvisibility=hidden -fvisibility-inlines-hidden -fno-strict-aliasing \
  -I "$src" "$src/guest_cpu_aot.cpp" "$src/guest_cpu_native.cpp" \
  "$src/host_call_arm64.S" \
  -Wl,-soname,libgow3cpu.so -Wl,--no-undefined -ldl -lm \
  -o "$out/libgow3cpu.so"
# Native AOT units depend on the libbbcpu ABI name, not another CPU engine.
"$cc" -shared -nostdlib -Wl,-soname,libbbcpu.so -Wl,--no-as-needed \
  -L "$out" -lgow3cpu -o "$out/libbbcpu.so"
"$readelf" -h "$out/libgow3cpu.so" | grep -Eq 'Machine:.*AArch64'
"$readelf" -d "$out/libgow3cpu.so" | grep -F '[libc.so]'
! "$readelf" -d "$out/libgow3cpu.so" | grep -Ei 'FEX|libFEXCore'
"$readelf" --dyn-syms --wide "$out/libgow3cpu.so" > "$out/symbols.txt"
for sym in guest_cpu_init guest_cpu_code guest_cpu_call guest_cpu_host_function \
    guest_cpu_thread_stack guest_cpu_set_gs guest_cpu_abandon \
    guest_cpu_thread_end guest_cpu_return_address guest_cpu_stack_pointer \
    guest_cpu_signal_regs guest_cpu_host_pc guest_cpu_handle_fault guest_cpu_hook \
    guest_cpu_tsc guest_cpu_tsc_frequency guest_context_get guest_context_set \
    bbr_dispatch bbr_dispatch_tail bbr_dirty_entry bbr_unwound; do
  grep -Eq "[[:space:]]$sym$" "$out/symbols.txt" || {
    echo "SotC AOT CPU missing exported function: $sym" >&2; exit 2;
  }
done
sha256sum "$out/libgow3cpu.so" "$out/libbbcpu.so" > "$out/native-cpu-sha256.txt"
echo "Strict SotC ARM64 AOT backend built; no FEX, no TSO compiler flag."
echo "Game execution still requires verified no-TSO libSotcAot.so."
