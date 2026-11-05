#!/usr/bin/env bash
# macOS/Apple-Silicon entrypoint for the Android ARM64 native build.
#
# This wrapper is intentionally separate from build.sh: it scopes Homebrew and
# local Bloodborne-Android dependencies to this invocation and does not modify
# the Linux build environment or its defaults.
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)

[[ $(uname -s) == Darwin ]] || {
    echo "build_mac_arm64.sh must run on macOS" >&2
    exit 1
}
case $(uname -m) in
    arm64|aarch64) ;;
    *) echo "build_mac_arm64.sh requires Apple Silicon (arm64)" >&2; exit 1 ;;
esac

brew_prefix() {
    local formula=$1 fallback=$2 prefix
    if command -v brew >/dev/null 2>&1; then
        prefix=$(brew --prefix "$formula" 2>/dev/null || true)
        if [[ -n $prefix && -d $prefix ]]; then
            printf '%s\n' "$prefix"
            return
        fi
    fi
    printf '%s\n' "$fallback"
}

llvm_prefix=${GOW3_LLVM_PREFIX:-$(brew_prefix llvm /opt/homebrew/opt/llvm)}
lld_prefix=${GOW3_LLD_PREFIX:-$(brew_prefix lld /opt/homebrew/opt/lld)}
export PATH="$llvm_prefix/bin:$lld_prefix/bin:$PATH"

# Bloodborne-Android is the FEX source used by this local port. Keep the
# override available for CI or another checkout, and fall back to the normal
# gow3 submodule when the sibling checkout is not present.
if [[ -z ${GOW3_FEX_SOURCE:-} ]]; then
    sibling_fex=$root/../Bloodborne-Android/third_party/FEX
    if [[ -f $sibling_fex/CMakeLists.txt ]]; then
        export GOW3_FEX_SOURCE=$sibling_fex
    fi
fi

# Homebrew Boost's CMake package directory contains the version number, so do
# not bake the currently installed version into the wrapper.
if [[ -z ${GOW3_BOOST_DIR:-} ]]; then
    boost_prefix=$(brew_prefix boost /opt/homebrew/opt/boost)
    if [[ -d $boost_prefix/lib/cmake ]]; then
        boost_dir=$(find "$boost_prefix/lib/cmake" -maxdepth 1 -type d -name 'Boost-*' -print |
            sort | tail -n 1)
        [[ -n $boost_dir ]] && export GOW3_BOOST_DIR=$boost_dir
    fi
fi

exec bash "$root/tools/android/build/build_arm64.sh" "$@"
