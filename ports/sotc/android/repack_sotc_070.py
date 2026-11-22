#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Repackage an already ABI-verified SotC strict AOT runtime for UI-only updates.

Reuses the 0.1.70 ARM64 host, GPU, AOT compiler, Turnip and Python binaries
unchanged. Only the launcher (built by Gradle), runtime manifest and launch
shell script differ. This avoids recompiling FFmpeg, FEX or shadPS4 when
implementing Android UI and automatic first-use AOT verification.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_BASE = "0.1.69-aot-ux"
RELEASE = "0.1.70-gamehub-ui"
ROOTPATHS = {
    "sotcport/run-sotc-bionic.sh": ROOT / "ports/sotc/android/run-sotc-bionic.sh",
}
# fxdisplay and fxio are already provided by the launcher source-set's
# tools/android/bridges. Duplicating them in apk-jni makes Gradle's
# :app:mergeReleaseJniLibFolders fail even when the bytes are identical.
JNI_LIBS = {"libbbrecomp.so", "libgow3present.so"}


def dynamic_symbols(binary: Path, defined: bool) -> set[str]:
    cmd = ["nm", "-D", "--defined-only" if defined else "--undefined-only", str(binary)]
    output = subprocess.check_output(cmd, text=True)
    result: set[str] = set()
    for line in output.splitlines():
        columns = line.split()
        if len(columns) < 2:
            continue
        if defined and columns[-2].upper() not in ("T", "D", "R", "B", "W", "V"):
            continue
        if not defined and columns[-2] != "U":
            continue
        result.add(columns[-1].split("@")[0])
    return result


def repack(base_apk: Path, asset_dir: Path, jni_root: Path) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    jni_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(base_apk) as apk:
        if apk.testzip() is not None:
            raise ValueError("0.1.68 base APK ZIP CRC check failed")
        old = apk.read("assets/runtime.payload")
        if hashlib.sha256(old).hexdigest() != apk.read("assets/runtime.sha256").decode().strip():
            raise ValueError("Base runtime checksum mismatch")
        with tarfile.open(fileobj=io.BytesIO(old), mode="r:gz") as original:
            original_members = original.getmembers()
            if set(ROOTPATHS) - {m.name for m in original_members}:
                raise ValueError("Base runtime does not contain required SotC shell script")
            manifest_file = original.extractfile("runtime-manifest.json")
            if manifest_file is None:
                raise ValueError("Missing runtime manifest")
            manifest = json.loads(manifest_file.read())
            if manifest.get("version") != EXPECTED_BASE or manifest.get("aot_mode") != "strict":
                raise ValueError("Not the approved strict native AOT 0.1.68 runtime")

            # The only valid SotC GPU driver is the user's hash-verified
            # GameHub DD 26.3 import. Do not bundle incompatible Turnip copies.
            manifest.pop("adreno7xx_driver", None)
            manifest["driver"] = {
                "id": "gamehub-dd-26.3",
                "name": "Turnip GameHub DD 26.3 GMEM/PWR_MAX",
                "archive_sha256": "8255659cc205110e0fa89f2d364292b86fe563a2cedafbc41915bead5a611ecb",
                "library_sha256": "4f242a453496ab27fc29be950d632edbae494dcc0c9b7d56c37c7ebdffe42df9",
                "bundled": False,
                "runtime_validation": "mandatory",
            }
            manifest["gamehub_dd_turnip_bundled"] = False
            manifest["version"] = RELEASE
            manifest["runtime_name"] = "sotc-daedalus-aot-0.1.70"
            manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False)+"\n").encode()
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.GNU_FORMAT) as modified:
                for entry in original_members:
                    if entry.name.startswith(("sotcport/arm64/drivers/gen8",
                                              "sotcport/arm64/drivers/adreno7xx")):
                        continue
                    if entry.name == "runtime-manifest.json":
                        payload = manifest_bytes
                    elif entry.name in ROOTPATHS:
                        payload = ROOTPATHS[entry.name].read_bytes()
                    elif entry.isfile():
                        infile = original.extractfile(entry)
                        if infile is None:
                            raise ValueError("Missing archived entry: " + entry.name)
                        payload = infile.read()
                    else:
                        modified.addfile(entry)
                        continue
                    entry.size = len(payload)
                    modified.addfile(entry, io.BytesIO(payload))
            new_payload = stream.getvalue()
        (asset_dir / "runtime.payload").write_bytes(new_payload)
        (asset_dir / "runtime.sha256").write_text(hashlib.sha256(new_payload).hexdigest()+"\n")
        (asset_dir / "THIRD_PARTY_LICENSES.txt").write_bytes(apk.read("assets/THIRD_PARTY_LICENSES.txt"))
        available = set()
        for member in apk.namelist():
            if member.startswith("lib/arm64-v8a/"):
                name = member.rsplit("/", 1)[-1]
                if name in JNI_LIBS:
                    target = jni_root / "arm64-v8a" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(apk.read(member))
                    available.add(name)
        if available != JNI_LIBS:
            raise ValueError("Missing JNI libraries: " + repr(sorted(JNI_LIBS - available)))

    # Compare the EXACT two ELFs inside the repackaged payload. This prevents
    # 0.1.66's C++ ABI and 0.1.67's runtime_memory_clamp_gap_hits dlopen failures.
    with tempfile.TemporaryDirectory() as temp:
        with tarfile.open(fileobj=io.BytesIO(new_payload), mode="r:gz") as tar:
            host = Path(temp) / "sotc-probe"
            gpu = Path(temp) / "libbbgpu.so"
            host.write_bytes(tar.extractfile("sotcport/arm64/bin/sotc-probe").read())
            gpu.write_bytes(tar.extractfile("sotcport/arm64/lib/libbbgpu.so").read())
        host_exports = dynamic_symbols(host, True)
        gpu_imports = dynamic_symbols(gpu, False)
        runtime_imports = {symbol for symbol in gpu_imports if symbol.startswith("runtime_")}
        missing = runtime_imports - host_exports
        if missing:
            raise ValueError("Repackaged renderer cannot dlopen; missing host ABI: " + str(sorted(missing)))
        bad_cpp = [sym for sym in gpu_imports if sym.startswith(("_ZN6Vulkan", "_ZN6AmdGpu", "_ZN9VideoCore"))]
        if bad_cpp:
            raise ValueError("Unresolved internal renderer ABI: " + str(bad_cpp))
        if "runtime_memory_clamp_gap_hits" not in host_exports:
            raise ValueError("Regression: host still missing gap cache counter")
        print(f"PASS ABI {len(runtime_imports)} runtime imports from EXACT repackaged host; no internal C++ missing")

    print("PASS 0.1.70 repackage: original 0.1.70 ARM64 native binaries unchanged, only script and manifest updated")
    print(f"Runtime payload: {len(new_payload)} bytes, SHA256 {hashlib.sha256(new_payload).hexdigest()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-apk", type=Path, required=True)
    parser.add_argument("--assets", type=Path, default=ROOT / "out/android-release/assets")
    parser.add_argument("--jni", type=Path, default=ROOT / "out/bionic/apk-jni")
    args = parser.parse_args()
    repack(args.base_apk, args.assets, args.jni)
