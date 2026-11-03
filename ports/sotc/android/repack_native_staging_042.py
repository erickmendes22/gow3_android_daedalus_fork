#!/usr/bin/env python3
"""Repackage 0.1.40 signed Android APK with ONLY native SotC libbbgpu.so rebuilt.

Preserves FEX, Turnip driver, entire runtime script and SotC INI, patches,
game preparation, native bridge and all other bytes from verified 0.1.40 APK.
Any runtime member change other than libbbgpu.so/manifest is a hard failure.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
from zipfile import ZipFile

OLD_VERSION="0.1.40-boot-test"
NEW_VERSION="0.1.42-boot-test"
RENDERER="sotcport/arm64/lib/libbbgpu.so"
MANIFEST="runtime-manifest.json"

def sha(b):
    return hashlib.sha256(b).hexdigest()

def repack(base_apk:Path,renderer:Path,root:Path):
    target=renderer.read_bytes()
    if len(target)<2_000_000 or not target.startswith(b"\x7fELF"):
        raise RuntimeError("Missing nonempty native ELF SotC libbbgpu.so")
    if b"SOTC_STAGING_LARGE_POW2" not in target:
        raise RuntimeError("Upstream staging pow2 allocator not compiled into renderer binary")
    outdir=root/"out/android-release/assets"
    outdir.mkdir(parents=True,exist_ok=True)
    out=outdir/"runtime.payload"
    hashes_old={}
    hashes_new={}
    with ZipFile(base_apk) as original:
        payload=original.read("assets/runtime.payload")
        if sha(payload)!=original.read("assets/runtime.sha256").decode().strip():
            raise RuntimeError("Original signed 0.1.40 runtime SHA256 mismatch")
        jni=root/"out/bionic/apk-jni/arm64-v8a/libgow3present.so"
        jni.parent.mkdir(parents=True,exist_ok=True)
        jni.write_bytes(original.read("lib/arm64-v8a/libgow3present.so"))
        for name in ("libfxdisplay.so","libfxio.so"):
            f=root/"tools/android/bridges/arm64-v8a"/name
            if not f.is_file() or f.stat().st_size<10000:
                raise RuntimeError("Missing original Android bridge "+name)
        with tarfile.open(fileobj=io.BytesIO(payload),mode="r:gz") as src:
            with tarfile.open(out,mode="w:gz",compresslevel=6) as dst:
                for entry in src:
                    if not entry.isfile():
                        dst.addfile(entry)
                        continue
                    current=src.extractfile(entry)
                    if current is None:
                        raise RuntimeError("Missing native runtime member "+entry.name)
                    before=current.read()
                    hashes_old[entry.name]=sha(before)
                    data=before
                    if entry.name==RENDERER:
                        if len(before)<2_000_000 or not before.startswith(b"\x7fELF"):
                            raise RuntimeError("Base renderer missing/corrupt")
                        if sha(before)==sha(target):
                            raise RuntimeError("Native renderer unchanged; patch not compiled")
                        data=target
                    elif entry.name==MANIFEST:
                        m=json.loads(before)
                        if m.get("version")!=OLD_VERSION:
                            raise RuntimeError("Not the verified 0.1.40 runtime")
                        m["version"]=NEW_VERSION
                        m["runtime_name"]="sotc-daedalus-bionic-0.1.42"
                        data=(json.dumps(m,indent=2)+"\n").encode()
                    hashes_new[entry.name]=sha(data)
                    revised=copy.copy(entry)
                    revised.size=len(data)
                    dst.addfile(revised,io.BytesIO(data))
    if not {RENDERER,MANIFEST,"sotcport/arm64/bin/sotc-probe",
            "sotcport/run-sotc-bionic.sh","sotcport/sotc.ini"}.issubset(hashes_old):
        raise RuntimeError("Missing original SotC 0.1.40 components")
    changed=[name for name in hashes_old if hashes_old[name]!=hashes_new[name]]
    if set(changed)!={RENDERER,MANIFEST}:
        raise RuntimeError("Unsafe payload changes: "+repr(changed))
    with tarfile.open(out,"r:gz") as tar:
        for name,original_hash in hashes_old.items():
            if name not in {RENDERER,MANIFEST}:
                f=tar.extractfile(name)
                if f is None or sha(f.read())!=original_hash:
                    raise RuntimeError("Original native data changed: "+name)
        if tar.extractfile(RENDERER).read()!=target:
            raise RuntimeError("New renderer not embedded in payload")
    digest=sha(out.read_bytes())
    (outdir/"runtime.sha256").write_text(digest+"\n")
    path=root/"out/release/sotc-native-staging-pow2-reuse-0.1.42.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({
        "source":"0.1.40-original-menu-four-optin",
        "new_version":"0.1.42-staging-pow2-coalesce",
        "only_changed_files":changed,
        "original_sha256":hashes_old,
        "repacked_sha256":hashes_new,
        "new_payload_sha256":digest,
        "renderer_patched_sha256":sha(target)
    },indent=2)+"\n")
    print("PASS: only libbbgpu.so + runtime manifest changed versus original 0.1.40")
    print("OLD renderer:",hashes_old[RENDERER])
    print("NEW renderer:",hashes_new[RENDERER])
    return path

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--base-apk",type=Path,required=True)
    parser.add_argument("--renderer",type=Path,required=True)
    parser.add_argument("--root",type=Path,default=Path("."))
    args=parser.parse_args()
    repack(args.base_apk,args.renderer,args.root)
