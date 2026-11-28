#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
out="$PWD/out/bionic"
stage="$out/apk-jni/arm64-v8a"
assets="$PWD/out/android-release/assets"
ndk="${GOW3_NDK:?Android NDK required}"
llvm="$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin"
mkdir -p "$stage" "$assets"
# Imported proprietary Qualcomm drivers require Android's vendor linker namespace.
# Build the audited upstream loader and hooks from immutable source; no prebuilt
# binary from another emulator and no replacement for the device's mapper ABI.
adreno_src="$out/adrenotools-src"
adreno_build="$out/adrenotools-build"
adreno_rev=8fae8ce254dfc1344527e05301e43f37dea2df80
if [[ ! -d "$adreno_src/.git" ]]; then
  git clone https://github.com/bylaws/libadrenotools.git "$adreno_src"
fi
git -C "$adreno_src" checkout --force "$adreno_rev"
git -C "$adreno_src" submodule update --init --recursive
# Custom driver failure must not masquerade as success on the system ICD.
python3 - "$adreno_src/src/hook/hook_impl.cpp" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
old='LOGI("hook_android_dlopen_ext: falling back!");'
new='''LOGI("hook_android_dlopen_ext: falling back!");
        if (hook_params->featureFlags & ADRENOTOOLS_DRIVER_CUSTOM) {
            std::fprintf(stderr, "GoW III imported Qualcomm: vendor hook failed; refusing system fallback\\n");
            return static_cast<void*>(nullptr);
        }'''
assert s.count(old)==1
s=s.replace(old,new)
old='return handle;\n    } else {'
new='std::fprintf(stderr, "GoW III imported Qualcomm: custom ICD loaded: %s%s\\n", hook_params->customDriverDir.c_str(), hook_params->customDriverName.c_str());\n        return handle;\n    } else {'
assert s.count(old)==1
p.write_text(s.replace(old,new))
PY
cmake -S "$adreno_src" -B "$adreno_build" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$ndk/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-30 \
  -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
cmake --build "$adreno_build" --parallel 2
for lib in libadrenotools.so libhook_impl.so libmain_hook.so libfile_redirect_hook.so libgsl_alloc_hook.so; do
  built_lib=$(find "$adreno_build" -name "$lib" -type f -print -quit)
  [[ -s "$built_lib" ]] || { echo "Missing Qualcomm namespace library $lib" >&2; exit 8; }
  "$llvm/llvm-readelf" -h "$built_lib" | grep -E 'Machine:.*AArch64'
  cp "$built_lib" "$stage/$lib"
done
mkdir -p "$assets/licenses"
cp "$adreno_src/LICENSE" "$assets/licenses/libadrenotools.txt"
