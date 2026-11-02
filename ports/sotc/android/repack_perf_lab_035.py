#!/usr/bin/env python3
"""SotC 0.1.35 Performance Lab.
Update ONLY the native runtime configuration files and Android launcher around
the signed 0.1.34 APK. The FEX executable, SotC Vulkan renderer, and native
driver files MUST remain byte-identical to the working 0.1.34 version.
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

NATIVE_FILES = (
    "sotcport/arm64/bin/sotc-probe",
    "sotcport/arm64/lib/libbbgpu.so",
)
EDITED_FILES = (
    "sotcport/run-sotc-bionic.sh",
    "sotcport/sotc.ini",
    "sotcport/sotc.default.ini",
    "runtime-manifest.json",
)
BEFORE = "0.1.34-boot-test"
AFTER = "0.1.35-boot-test"

def sha(blob):
    return hashlib.sha256(blob).hexdigest()

def build(base_apk, root):
    cfg_script = root/"ports/sotc/android/package_sotc_runtime.py"
    manifest_options = json.loads((root/"ports/sotc/android/sotc_perf_lab_035.json").read_text())
    package_source = cfg_script.read_text()
    match = re.search(r"defaults='''(.*?)'''", package_source, re.S)
    if match is None:
        raise RuntimeError("SotC INI defaults cannot be located")
    ini = match.group(1).encode("utf-8")
    runner = (root/"ports/sotc/android/run-sotc-bionic.sh").read_bytes()
    for entry in manifest_options["toggles"]+manifest_options["choices"]:
        key,env,default = entry["key"],entry["env"],entry["def"]
        if (key+"="+default+"\n").encode("utf-8") not in ini:
            raise RuntimeError("Missing INI setting "+key)
        if ('"'+env+'"').encode() not in (root/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_bytes():
            raise RuntimeError("Setting not connected to Android launcher: "+env)
        if entry["type"]=="toggle" and ("export "+env+"=").encode() not in runner:
            raise RuntimeError("Native toggle is not exported: "+env)
    for required in (
        b"export SOTC_UPLOAD_BUDGET_MB=0",
        b"export SOTC_VM_RANGE_CACHE=",
        b"export BB_READBACKS=",
        b"export SOTC_RB_STREAM=",
        b"export SOTC_RB_STREAM_MAX_KB=",
        b"export SOTC_FLUSH_EVERY=256",
    ):
        if required not in runner:
            raise RuntimeError("Working runtime guard absent: "+repr(required))
    outdir=root/"out/android-release/assets"
    outdir.mkdir(parents=True,exist_ok=True)
    output=outdir/"runtime.payload"
    hashes={}
    modified=set()
    with zipfile.ZipFile(base_apk) as apk:
        original_payload=apk.read("assets/runtime.payload")
        expected=apk.read("assets/runtime.sha256").decode().strip()
        if sha(original_payload)!=expected:
            raise RuntimeError("Original 0.1.34 runtime payload failed SHA256 check")
        original_jni=apk.read("lib/arm64-v8a/libgow3present.so")
        if len(original_jni)<10000:
            raise RuntimeError("Original AHB JNI presenter library missing")
        target=root/"out/bionic/apk-jni/arm64-v8a/libgow3present.so"
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(original_jni)
        for name in ("libfxdisplay.so","libfxio.so"):
            bridge=root/"tools/android/bridges/arm64-v8a"/name
            if not bridge.is_file() or bridge.stat().st_size<10000:
                raise RuntimeError("Required Android Bionic bridge missing: "+name)
        with tarfile.open(fileobj=io.BytesIO(original_payload), mode="r:gz") as src:
            with tarfile.open(output, mode="w:gz",compresslevel=6) as dst:
                for member in src:
                    if not member.isfile():
                        dst.addfile(member)
                        continue
                    inp=src.extractfile(member)
                    if inp is None:
                        raise RuntimeError("Unexpected missing entry "+member.name)
                    if member.name in EDITED_FILES:
                        before=inp.read()
                        if member.name=="sotcport/run-sotc-bionic.sh":
                            data=runner
                        elif member.name.endswith(".ini"):
                            data=ini
                        else:
                            obj=json.loads(before)
                            if obj.get("version")!=BEFORE:
                                raise RuntimeError("Runtime source is not original 0.1.34")
                            obj["version"]=AFTER
                            obj["runtime_name"]="sotc-daedalus-bionic-0.1.35"
                            data=(json.dumps(obj,indent=2)+"\n").encode("utf-8")
                        m=copy.copy(member)
                        m.size=len(data)
                        dst.addfile(m,io.BytesIO(data))
                        modified.add(member.name)
                    elif member.name in NATIVE_FILES or (
                            member.name.startswith("sotcport/arm64/drivers/") and
                            member.name.endswith((".so",".a"))):
                        data=inp.read()
                        hashes[member.name]=sha(data)
                        dst.addfile(member,io.BytesIO(data))
                    else:
                        dst.addfile(member,inp)
    if modified!=set(EDITED_FILES):
        raise RuntimeError("Runtime configuration member set mismatch: "+str(modified))
    if not set(NATIVE_FILES).issubset(hashes):
        raise RuntimeError("Original SotC ELF executable or renderer missing")
    with tarfile.open(output,mode="r:gz") as staged:
        assert staged.extractfile("sotcport/run-sotc-bionic.sh").read()==runner
        for name in ("sotcport/sotc.ini","sotcport/sotc.default.ini"):
            assert staged.extractfile(name).read()==ini
        assert json.load(staged.extractfile("runtime-manifest.json"))["version"]==AFTER
        for name,digest in hashes.items():
            assert sha(staged.extractfile(name).read())==digest, name
    new_sha=sha(output.read_bytes())
    (outdir/"runtime.sha256").write_text(new_sha+"\n")
    fingerprints=root/"out/release/sotc-native-preserved-0.1.35.json"
    fingerprints.parent.mkdir(parents=True,exist_ok=True)
    fingerprints.write_text(json.dumps({
        "source":"0.1.34-sequential-readback",
        "target":"0.1.35-performance-lab",
        "changed_entries":sorted(modified),
        "native_elf_sha256_unchanged":hashes,
        "new_payload_sha256":new_sha,
        "controls":len(manifest_options["toggles"])+len(manifest_options["choices"]),
    },indent=2)+"\n")
    print("PASS: 0.1.35 performance lab: native FEX and renderer identical to 0.1.34")
    for name,digest in sorted(hashes.items()):
        print("Native unchanged:",name,digest)
    return fingerprints

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--base-apk",type=Path,required=True)
    parser.add_argument("--root",type=Path,default=Path("."))
    args=parser.parse_args()
    build(args.base_apk,args.root)
