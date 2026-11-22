#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shadow of the Colossus: compile the user's prepared PS4 image to ARM64 AOT.

Phase 1 ONLY: produce and verify libSotcAot.so. Production FEX, game files,
the verified patch catalogue, and readback preferences stay untouched.
The supplied bb-recomp compiler must generate ARM64 without --tso.
No FEX or TSO codegen is permitted in the native guest execution target.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cmdline_image import embed as embed_cmdline

HEADER = struct.Struct("<8s12Q")
SUPPORTED = {"CUSA08809", "CUSA08034"}
AOT_COMPILER_VERSIONS = ("2",)  # official bb-recomp 1.3.0 codegen, no --tso
AOT_FLAGS = ("--resume-entries", "--no-callee-saved")
MAX_IMAGE = 512 * 1024 * 1024
MAX_PATCHES = 10000
PATCH_BASE = 0x400000
# Explicit synchronization remains necessary for guest runtime correctness.
# The compiler command NEVER enables x86 TSO instrumentation.

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def boot_info(path: Path) -> dict:
    size_on_disk = path.stat().st_size
    with path.open("rb") as f:
        raw = f.read(HEADER.size)
        if len(raw) != HEADER.size:
            raise ValueError("Truncated BBPROBE5 header")
        magic, image_bytes, entry, ns, nr, ni, flags, procparam, *tls_mod = HEADER.unpack(raw)
        mc = tls_mod[-1]
        if magic != b"BBPROBE5":
            raise ValueError("SotC AOT requires the original BBPROBE5 linked image")
        if not 0 < image_bytes <= MAX_IMAGE or not 0 < ns <= 64 or not 0 < mc <= 16:
            raise ValueError("BBPROBE5 invalid image/module/segment counts")
        if not 0 <= entry < image_bytes or ni > 100000 or nr > 4000000:
            raise ValueError("BBPROBE5 invalid entry/import/relocation counts")
        f.seek(HEADER.size + 56 * mc)
        binding = f.read(8)
        if len(binding) != 8:
            raise ValueError("BBPROBE5 truncated bindings")
        nb, = struct.unpack("<Q", binding)
        if nb > ni:
            raise ValueError("BBPROBE5 invalid bindings count")
        table_bytes = HEADER.size + 56*mc + 8 + 24*nb + 24*ns + 128*ni + 32*nr
        if table_bytes + image_bytes != size_on_disk:
            raise ValueError("BBPROBE5 inconsistent table/image length")
        return dict(image_bytes=image_bytes, entry=entry, segments=ns,
                    relocations=nr, imports=ni, bindings=nb, modules=mc,
                    table_bytes=table_bytes, image_sha256=sha256_region(path,table_bytes))

def sha256_region(path: Path, offset: int) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        f.seek(offset)
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def patch_records(path: Path, image_bytes: int) -> list[tuple[int,bytes]]:
    data=path.read_bytes()
    if len(data)<24:
        raise ValueError("Missing BBPATCH2 file")
    magic,base,count=struct.unpack_from("<8sQQ",data)
    if magic!=b"BBPATCH2" or base!=PATCH_BASE or count>MAX_PATCHES:
        raise ValueError("Unexpected SotC BBPATCH2 header/patch base")
    records=[]; cursor=24; ranges=[]
    for i in range(count):
        if cursor+16>len(data):
            raise ValueError(f"Truncated patch #{i}")
        off,n=struct.unpack_from("<QQ",data,cursor);cursor+=16
        target=off
        if n<1 or n>4096 or target>image_bytes or n>image_bytes-target or cursor+n>len(data):
            raise ValueError(f"Patch #{i} outside image or larger than native runtime limit")
        for start,end in ranges:
            if start<target+n and target<end:
                raise ValueError("Overlapping SotC patch records are not AOT-safe")
        ranges.append((target,target+n));records.append((target,data[cursor:cursor+n]));cursor+=n
    if cursor!=len(data):
        raise ValueError("Trailing BBPATCH2 data")
    return records

def stage_native_boot(boot: Path, patches: Path, dest: Path) -> dict:
    info=boot_info(boot)
    records=patch_records(patches,info["image_bytes"])
    # src/probe.c apply_patches() uses guest image-relative BBPATCH2 offsets.
    # The 0x400000 header is ONLY the origin for pointer relocation values.
    # Adding 0x400000 corrupts executable metadata, including .eh_frame FDEs.
    # Important: no game original modified; patch all verified guest-code and
    # guest-data bytes BEFORE translation, or the AOT units would be stale.
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    try:
        shutil.copyfile(boot,tmp)
        with tmp.open("r+b") as f:
            for off,data in records:
                f.seek(info["table_bytes"]+off)
                f.write(data)
        if boot_info(tmp)["image_bytes"]!=info["image_bytes"]:
            raise ValueError("AOT patch staging changed the image length")
        os.replace(tmp,dest)
    finally:
        tmp.unlink(missing_ok=True)
    return {**info,"patched_image_sha256":sha256_region(dest,info["table_bytes"]),
            "patch_count":len(records),"patch_sha256":sha256(patches)}

def validate_game(prepared: Path, game: Path) -> dict:
    if prepared.resolve()==game.resolve() or game.resolve() in prepared.resolve().parents:
        raise ValueError("AOT work folder must not be inside the player's game")
    eboot=game/"eboot.bin"
    stamp=prepared/"analysis.json"
    identity=prepared/".sotc-android-prepare.json"
    for p in (eboot,game/"sce_sys/param.sfo",game/"sce_module/libc.prx",
              game/"sce_module/libSceFios2.prx",stamp,identity):
        if not p.is_file():
            raise ValueError(f"Required local SotC input absent: {p.name}")
    analysis=json.loads(stamp.read_text())
    prepare=json.loads(identity.read_text())
    game_sha=sha256(eboot)
    if game_sha!=analysis.get("source_sha256"):
        raise ValueError("Prepared BBPROBE5 source does not match selected eboot; regenerate")
    title=prepare.get("title_id")
    if title not in SUPPORTED:
        raise ValueError("Unsupported game title (only verified EU 1.01/US 1.00)")
    return {"title_id":title,"eboot_sha256":game_sha}

def compiler_command(compiler: Path,game: Path,boot: Path,so: Path,stats:Path,
                     bundle: Path|None,jobs:int,shards:int)->list[str]:
    command=[str(compiler),"--boot",str(boot),"--game-dir",str(game),
             "--so",str(so),"--stats",str(stats),"--jobs",str(jobs),
             "--shards",str(shards),"--target","aarch64","--host","armv8.2",
             *AOT_FLAGS,"-O1","--no-nice","--progress","--resume"]
    if bundle:
        command+=["--bundle-dir",str(bundle)]
    return command

def verify_native(so: Path, stats: Path, meta_file: Path) -> dict:
    if not so.is_file() or not meta_file.is_file() or not stats.is_file():
        raise ValueError("AOT compiler did not produce library, JSON, and stats")
    with so.open("rb") as f:
        header=f.read(20)
    if len(header)<20 or header[:4]!=b"\x7fELF" or struct.unpack_from("<H",header,18)[0]!=183:
        raise ValueError("AOT output is not an AArch64 shared library")
    meta=json.loads(meta_file.read_text())
    version=meta.get("compiler_version","")
    if meta.get("abi_version")!=2 or version not in AOT_COMPILER_VERSIONS:
        raise ValueError("AOT ABI/compiler version not validated")
    if meta.get("so_sha256")!=sha256(so):
        raise ValueError("AOT shared library SHA256 mismatch")
    raw=stats.read_text(errors="replace")
    m=re.search(r"units with bbr_trap \(unsupported ops\):\s*(\d+)\s*\(([\d.]+)%\)",raw)
    if not m or "LoadMemTSO" in raw or "StoreMemTSO" in raw:
        raise ValueError("Guest TSO operations appeared despite no-TSO codegen or coverage report missing")
    dirty,percent=int(m.group(1)),float(m.group(2))
    total=int(meta.get("unit_count",0))
    # Strict AOT has no JIT fallback. Even ONE bbr_trap can crash in gameplay:
    # do not promote a library with unsupported guest instructions. Past builds
    # accepted 10/67951 units, hiding up to 109 fatal trap sites.
    if total<=0 or dirty>total or dirty!=0 or percent!=0.0:
        raise ValueError(f"AOT has fatal unsupported instructions: {dirty}/{total} ({percent}%) - stop before APK")
    return dict(compiler_version=version,unit_count=total,
                unsupported_units=dirty,unsupported_percent=percent,
                library_sha256=sha256(so),abi_version=2)

def main(argv:list[str]|None=None)->int:
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--game",type=Path,required=True)
    a.add_argument("--prepared",type=Path,required=True,
                   help="Current SotC preparation folder with BBPROBE5, BBPATCH2 and analysis.json")
    a.add_argument("--out",type=Path,required=True,help="Private AOT working directory")
    a.add_argument("--compiler",type=Path,help="Android ARM64 bb-recomp; do not enable --tso")
    a.add_argument("--bundle-dir",type=Path,help="LLVM native helper bundle")
    a.add_argument("--jobs",type=int,default=3)
    a.add_argument("--shards",type=int,default=64)
    a.add_argument("--dry-run",action="store_true")
    args=a.parse_args(argv)
    if not 1<=args.jobs<=16 or not 1<=args.shards<=4096:
        a.error("Invalid jobs/shards")
    report={"backend":"sotc-arm64-aot-experimental","tso":"disabled",
            "fex_runtime_required_for_current_release":False,
            "aot_execution_integrated":False,
            "status":"preflight"}
    dest=args.out.resolve()
    try:
        for folder in (args.game,args.prepared):
            if not folder.is_dir():
                raise ValueError(f"Input folder missing: {folder}")
        game=validate_game(args.prepared,args.game)
        if dest==args.game.resolve() or args.game.resolve() in dest.parents:
            raise ValueError("AOT output may not overwrite the game dump")
        dest.mkdir(parents=True,exist_ok=True)
        boot=args.prepared/"boot-linked.bin"
        patches=args.prepared/"patches.bin"
        # Preserve SotC command-line options before AOT code generation.
        patch_only=dest/"native-boot-patches.bin"
        info=stage_native_boot(boot,patches,patch_only)
        cmdline=args.prepared/"cmdline.bin"
        if not cmdline.is_file():
            raise ValueError("Prepared engine command line missing")
        native=dest/"native-boot-linked.bin"
        cmdline_info=embed_cmdline(patch_only,cmdline,native)
        so=dest/"aot/libSotcAot.so"
        stats=dest/"aot/compile.txt"
        cmd=compiler_command(args.compiler or Path("/unconfigured/compiler"),
                             args.game,native,so,stats,args.bundle_dir,args.jobs,args.shards)
        report.update(game=game,image=info,cmdline=cmdline_info,
                      cmdline_sha256=sha256(cmdline), guest_cpu_model="ARM64 AOT without FEX/TSO",
                      original_boot_sha256=sha256(boot),
                      aot_boot_sha256=sha256(native),
                      command=cmd,status="preflight_ok")
        (dest/"aot-report.json").write_text(json.dumps(report,indent=2)+"\n")
        if args.dry_run:
            print("SotC AOT: verified and staged patched BBPROBE5, no compilation or FEX switch.")
            return 0
        if not args.compiler or not args.compiler.is_file():
            raise ValueError("AOT compiler not supplied; FEX remains active")
        so.parent.mkdir(parents=True,exist_ok=True)
        result=subprocess.run(cmd,check=False)
        if result.returncode:
            raise ValueError(f"Native compiler failed with status {result.returncode}")
        report["coverage"]=verify_native(so,stats,so.with_suffix(".json"))
        report["status"]="aot_library_built_not_executed"
        (dest/"aot-report.json").write_text(json.dumps(report,indent=2)+"\n")
        print(f"SotC ARM64 AOT library verified: {so}; FEX runtime unchanged")
        return 0
    except (OSError,ValueError,json.JSONDecodeError) as e:
        report["status"]="blocked"
        report["reason"]=str(e)
        if dest.is_dir():
            (dest/"aot-report.json").write_text(json.dumps(report,indent=2)+"\n")
        print(f"SotC AOT preflight: {e}",file=sys.stderr)
        return 1

if __name__=="__main__":
    sys.exit(main())
