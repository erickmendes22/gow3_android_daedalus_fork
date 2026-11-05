#!/usr/bin/env bash
# Stage the debug runtime payload for the Gradle debug source set
# (android-launcher/app/build.gradle.kts: out/android-debug/assets) and the LOCAL_*
# Turnip/LSFG inputs that build_release_runtime.py --profile debug reads.
#
# Idempotent: only rebuilds the runtime archive when it is missing or
# GOW3_REBUILD_DEBUG_RUNTIME=1; otherwise it validates and re-stages the existing one.
# Called both by build_debug_apk.sh and by the Gradle preDebugBuild hook (Android Studio).
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
cd -- "$script_dir/../../.."

if [[ ${GOW3_REBUILD_DEBUG_RUNTIME:-0} == 1 || ! -f out/debug/runtime.tar.gz ]]; then
    # The debug runtime reuses the locally built Turnip/LSFG. build_release_runtime.py
    # --profile debug reads them from .local-deps/android/{turnip,turnip-gen8}, so stage
    # the out/arm64/ artifacts there first (overwrites stale copies).
    stage_local_input() { # src_dir name
        local src=$1 dst=".local-deps/android/$2"
        if [[ -d $src ]]; then
            mkdir -p "$dst"
            cp -R "$src/." "$dst/"
            echo "staged $2 <- $src"
        else
            echo "stage_debug_runtime: no $src (run build_android_runtime.sh first)" >&2
            return 1
        fi
    }
    stage_local_input out/arm64/turnip turnip
    stage_local_input out/arm64/turnip-gen8 turnip-gen8
    python3 tools/android/runtime/build_release_runtime.py --profile debug
else
    python3 tools/android/runtime/validate_runtime_archive.py out/debug/runtime.tar.gz \
        --digest out/debug/runtime.sha256 --manifest tools/android/debug/runtime-manifest.json
fi

mkdir -p out/android-debug/assets
cp out/debug/runtime.tar.gz out/android-debug/assets/runtime.payload
cp out/debug/runtime.sha256 out/android-debug/assets/runtime.sha256
echo "Debug runtime payload: out/android-debug/assets/runtime.payload"
