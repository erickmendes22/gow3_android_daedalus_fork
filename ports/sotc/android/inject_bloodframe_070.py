#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Install REAL Bloodframe 2.0 and native presenter into v0.1.70 runtime payload.

Inputs are independently GitHub-Actions-verified ARM64 artifacts, not library
names fabricated in the launcher's UI. The game ELF/native AOT toolchain stays
identical to the tested 0.1.69 baseline. Fail closed on missing symbols, altered
model hashes, mismatched host ABI or non-Android binaries.
"""
import argparse, hashlib, io, json, os, subprocess, tarfile, tempfile
from pathlib import Path

EXPECTED_MODEL={
    "LICENSE":"e990112837dcd5af880065d292f22f394f87c69912f957eabc54dc0285c6a7fc",
    "model/mixture.spv":"f5395a370e03783273c68295c1b11215e8c0c7c978e07299b68d7e843d6c0e8e",
    "model/ops.spv":"431ec6d0224111435a62e9e1235d844cc9180083e9e5c79461b47d46a2b950ea",
    "model/transport.spv":"d2285a08b046fcb40ef63254589df3e1defa43e11e8f1026dd9a10c922db992d",
    "model/weights.bin":"08ed3acfefa71a6d29a208e9a64c73d6593bfc2e83eb0230fe4f8d62ff7ea781",
}
def sha(b):return hashlib.sha256(b).hexdigest()

def syms(path,defined):
    cmd=["nm","-D","--defined-only" if defined else "--undefined-only",str(path)]
    result=subprocess.run(cmd,text=True,capture_output=True,check=True).stdout
    x={}
    for line in result.splitlines():
        c=line.split()
        if len(c)>=2:x[c[-1].split("@")[0]]=c[-2]
    return set(x)

def inject(assets:Path,render:Path,bloodframe:Path):
    payload=assets/"runtime.payload"
    digest=assets/"runtime.sha256"
    original=payload.read_bytes()
    assert sha(original)==digest.read_text().strip(),"Original payload checksum mismatch"
    render_bytes=render.read_bytes()
    bf=bloodframe/"lib/libbloodframe.so"
    bf_bytes=bf.read_bytes()
    for path,data in ((render,render_bytes),(bf,bf_bytes)):
        assert len(data)>500000 and data[:4]==b"\x7fELF",str(path)+" is not an ELF"
        assert data[18:20]==b"\xb7\x00",str(path)+" is not an ARM64 ELF"
    for symbol in ("bb_lsfg_present","bb_lsfg_init_v2","bb_lsfg_create_context"):
        assert symbol in syms(bf,True),"Bloodframe 2.0 lacks "+symbol
    verified={}
    for name,digest_expected in EXPECTED_MODEL.items():
        path=bloodframe/"mako-fg"/name
        data=path.read_bytes()
        if sha(data)!=digest_expected:raise ValueError("MAKO-FG model hash mismatch: "+name)
        verified["sotcport/mako-fg/"+name]=data
    release=(bloodframe/"mako-fg/release.json").read_bytes()
    upstream=json.loads(release)
    assert upstream["files"]==EXPECTED_MODEL,"MAKO release SHA manifest mismatch"
    assert "NC" in upstream["license"],"MAKO noncommercial license missing"
    verified["sotcport/mako-fg/release.json"]=release
    verified["sotcport/arm64/lib/libbloodframe.so"]=bf_bytes

    # A byte-for-byte matching host ABI is crucial: 0.1.67 used to compile
    # successfully and crash during dlopen due to an unresolved VM counter.
    with tempfile.TemporaryDirectory() as work:
        dest=Path(work)
        with tarfile.open(fileobj=io.BytesIO(original),mode="r:gz") as t:
            host=t.extractfile("sotcport/arm64/bin/sotc-probe").read()
            existing=t.extractfile("sotcport/arm64/lib/libbbgpu.so").read()
        (dest/"sotc-probe").write_bytes(host)
        (dest/"libbbgpu.so").write_bytes(render_bytes)
        missing={x for x in syms(dest/"libbbgpu.so",False) if x.startswith("runtime_")} - syms(dest/"sotc-probe",True)
        assert not missing, "Native Bloodframe presenter has unresolved host ABI symbols: "+str(sorted(missing))
        native_undefined=syms(dest/"libbbgpu.so",False)
        internal=[x for x in native_undefined if x.startswith(("_ZN6Vulkan","_ZN6AmdGpu","_ZN9VideoCore"))]
        assert not internal, "Unresolved internal C++ renderer symbols: "+str(internal)
        assert b"SOTC BLOODFRAME: ACTIVE" in render_bytes,"Fake/missing native FG presenter"
        assert b"bb_lsfg_present" in render_bytes,"Native renderer doesn't call Bloodframe engine"
    replacements={
        "sotcport/arm64/lib/libbbgpu.so":render_bytes,
        **verified,
    }
    out=io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(original),mode="r:gz") as inp:
        with tarfile.open(fileobj=out,mode="w:gz",format=tarfile.GNU_FORMAT) as tar:
            seen=set()
            for entry in inp.getmembers():
                if entry.name=="runtime-manifest.json":
                    manifest=json.load(inp.extractfile(entry))
                    assert manifest["version"]=="0.1.70-gamehub-ui"
                    assert manifest["driver"]["id"]=="gamehub-dd-26.3"
                    manifest["bloodframe"]={
                        "engine":"Bloodframe 2.0",
                        "renderer":"Vulkan AHardwareBuffer external-memory + sync-fd",
                        "model":"MAKO-FG V1.24",
                        "license":"CC BY-NC 4.0; non-commercial only",
                        "mode":"opt-in",
                        "frames_per_game_frame":2,
                        "source_commit":"f4ac713aef58d9403a136e179b3b0d163d85eb66",
                    }
                    data=(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n").encode()
                elif entry.name in replacements:
                    data=replacements.pop(entry.name)
                elif entry.isfile():
                    data=inp.extractfile(entry).read()
                else:
                    tar.addfile(entry);continue
                entry.size=len(data)
                tar.addfile(entry,io.BytesIO(data))
                seen.add(entry.name)
            # New libbloodframe and model files were not in 0.1.69.
            for name,data in replacements.items():
                info=tarfile.TarInfo(name);info.mode=0o644;info.size=len(data)
                tar.addfile(info,io.BytesIO(data))
    new=out.getvalue()
    payload.write_bytes(new)
    digest.write_text(sha(new)+"\n")
    print("SOTC BLOODFRAME VALID: native ARM64 shared library",len(bf_bytes),
          "Vulkan renderer",len(render_bytes),"MAKO-FG model SHA-verified")
    print("SOTC BLOODFRAME VALID: same game CPU/AOT and original GameHub driver; payload",len(new),sha(new))

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--assets",type=Path,required=True)
    ap.add_argument("--renderer",type=Path,required=True)
    ap.add_argument("--bloodframe",type=Path,required=True)
    args=ap.parse_args()
    inject(args.assets,args.renderer,args.bloodframe)
