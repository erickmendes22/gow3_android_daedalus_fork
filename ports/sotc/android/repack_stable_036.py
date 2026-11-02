#!/usr/bin/env python3
"""SotC 0.1.36: preserve *all* 0.1.34 runtime files, except manifest version.

0.1.35 forcibly exported 26 settings despite promising the same defaults.
This rolls that entire change back. The Android launcher offers only a simple
stable/experimental profile. Native FEX, Vulkan, driver, shell and INI remain
byte-for-byte IDENTICAL to the measured 0.1.34 APK.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile

OLD_VERSION="0.1.34-boot-test"
NEW_VERSION="0.1.36-boot-test"
NATIVE_REQUIRED={
    "sotcport/arm64/bin/sotc-probe",
    "sotcport/arm64/lib/libbbgpu.so",
}
UNCHANGED_CONFIGURATION={
    "sotcport/run-sotc-bionic.sh",
    "sotcport/sotc.ini",
    "sotcport/sotc.default.ini",
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main(source_apk: Path, root: Path):
    # Compare archived runtime settings against original pinned 0.1.34 sources.
    shell=(root/"ports/sotc/android/run-sotc-bionic.sh").read_bytes()
    text=(root/"ports/sotc/android/package_sotc_runtime.py").read_text()
    match=re.search(r"defaults='''(.*?)'''",text,re.S)
    if not match:
        raise RuntimeError("Original SotC 0.1.34 default configuration missing")
    ini=match.group(1).encode()
    if b"SOTC_FLUSH_EVERY" in shell or b"SOTC_RB_AHEAD=" in shell:
        raise RuntimeError("Experimental 0.1.35 forced flag leaked into stable runtime")
    if b"SOTC_VM_RANGE_CACHE=" not in shell or b"SOTC_RB_STREAM=" not in shell:
        raise RuntimeError("Known-good 0.1.34 VM cache / stream no longer enabled")
    if b"sotc_readbacks=2" not in ini or b"sotc_rb_stream=1" not in ini:
        raise RuntimeError("Known-good precise readback defaults changed")
    outdir=root/"out/android-release/assets"
    outdir.mkdir(parents=True,exist_ok=True)
    out=outdir/"runtime.payload"
    original_sha={}
    new_sha={}
    with zipfile.ZipFile(source_apk) as original:
        payload=original.read("assets/runtime.payload")
        if sha(payload)!=original.read("assets/runtime.sha256").decode().strip():
            raise RuntimeError("0.1.34 APK payload hash mismatch")
        presenter=original.read("lib/arm64-v8a/libgow3present.so")
        if len(presenter)<10000:
            raise RuntimeError("AHardwareBuffer presenter absent")
        jni=root/"out/bionic/apk-jni/arm64-v8a/libgow3present.so"
        jni.parent.mkdir(parents=True,exist_ok=True)
        jni.write_bytes(presenter)
        for bridge_name in ("libfxdisplay.so","libfxio.so"):
            bridge=root/"tools/android/bridges/arm64-v8a"/bridge_name
            if not bridge.is_file() or bridge.stat().st_size<10000:
                raise RuntimeError("Missing native Android bridge: "+bridge_name)
        with tarfile.open(fileobj=io.BytesIO(payload),mode="r:gz") as src:
            with tarfile.open(out,mode="w:gz",compresslevel=6) as dst:
                for member in src:
                    if not member.isfile():
                        dst.addfile(member)
                        continue
                    f=src.extractfile(member)
                    if f is None:
                        raise RuntimeError("Missing payload file: "+member.name)
                    data=f.read()
                    original_sha[member.name]=sha(data)
                    if member.name in UNCHANGED_CONFIGURATION:
                        want=shell if member.name.endswith(".sh") else ini
                        if data!=want:
                            raise RuntimeError("Source 0.1.34 native settings drift: "+member.name)
                    if member.name=="runtime-manifest.json":
                        record=json.loads(data)
                        if record.get("version")!=OLD_VERSION:
                            raise RuntimeError("Refusing to package runtime other than 0.1.34")
                        record["version"]=NEW_VERSION
                        record["runtime_name"]="sotc-daedalus-bionic-0.1.36"
                        data=(json.dumps(record,indent=2)+"\n").encode()
                    new_sha[member.name]=sha(data)
                    updated=copy.copy(member)
                    updated.size=len(data)
                    dst.addfile(updated,io.BytesIO(data))
    if not NATIVE_REQUIRED.issubset(original_sha) or not UNCHANGED_CONFIGURATION.issubset(original_sha):
        raise RuntimeError("Missing required native binaries or source settings")
    changed=[key for key in original_sha if original_sha[key]!=new_sha[key]]
    if changed!=["runtime-manifest.json"]:
        raise RuntimeError("Not a pure 0.1.34 runtime rollback: "+repr(changed))
    with tarfile.open(out,"r:gz") as packed:
        assert json.load(packed.extractfile("runtime-manifest.json"))["version"]==NEW_VERSION
        for name, digest in original_sha.items():
            if name!="runtime-manifest.json":
                assert sha(packed.extractfile(name).read())==digest, name
    digest=sha(out.read_bytes())
    (outdir/"runtime.sha256").write_text(digest+"\n")
    report=root/"out/release/sotc-native-identical-0.1.36.json"
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps({
        "baseline":"0.1.34-sequential-readback",
        "version":"0.1.36-stable-simple",
        "only_changed_runtime_file":changed,
        "all_original_file_sha256":original_sha,
        "new_payload_sha256":digest,
        "experimental_native_flags_exported_in_stable":False,
    },indent=2)+"\n")
    print("PASS: all 0.1.34 native/configuration bytes unchanged, except version manifest")
    print("Native FEX:",original_sha["sotcport/arm64/bin/sotc-probe"])
    print("Native Vulkan:",original_sha["sotcport/arm64/lib/libbbgpu.so"])
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--base-apk",type=Path,required=True)
    parser.add_argument("--root",type=Path,default=Path("."))
    args=parser.parse_args()
    main(args.base_apk,args.root)
