#!/usr/bin/env python3
"""Assemble an Android/Bionic development tree without changing upstream source.

Source-of-truth for game HLE/renderer remains JulioCacko/The-Order-1886_pc.
This script only overlays the explicitly modified Android CPU-boundary files.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess

UPSTREAM = "c53cd01d032995fe622033623ab64b4cf6b02233"
DONOR = "b3a7c3d5e916cf8f4622192c0faa9383ebd77c00"
FILES = [
    "src/probe.c", "src/runtime.c", "src/runtime.h", "src/runtime_thread.c",
    "src/guest_cpu.h", "src/runtime_cpu.c", "cpu/guest_cpu_fex.cpp",
    "cpu/host_call_arm64.S", "cpu/bionic_compat.h",
    "cpu/fex_project.cmake", "cpu/order1886cpu.cmake",
]

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="The Order PC checkout")
    parser.add_argument("--output", type=Path, required=True, help="New, separate staging directory")
    parser.add_argument("--overlay", type=Path, default=Path(__file__).resolve().parents[1] / "overlay")
    parser.add_argument("--allow-other-revision", action="store_true")
    args = parser.parse_args()
    source, output, overlay = (v.expanduser().resolve() for v in (args.source,args.output,args.overlay))
    if not (source / "src/probe.c").is_file() or not (source / "gpu/CMakeLists.txt").is_file():
        parser.error("Expected a complete The Order PC source checkout")
    if output == source or source in output.parents or output in source.parents:
        parser.error("Refusing to overwrite or stage inside the upstream tree")
    if output.exists():
        parser.error("Output directory exists; never overlay a potentially modified tree")
    if not args.allow_other_revision:
        sha = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],text=True).strip()
        if sha != UPSTREAM:
            parser.error(f"Source revision {sha} is not the verified {UPSTREAM}; use --allow-other-revision deliberately")
    for path in FILES:
        if not (overlay / path).is_file():
            parser.error(f"Missing Android overlay: {path}")
    shutil.copytree(source,output,symlinks=True,ignore=shutil.ignore_patterns(".git","out","user","__pycache__","*.pyc"))
    for path in FILES:
        dest=output/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(overlay/path,dest)
    meta={
        "project":"The Order: 1886 Android Bionic (development only)",
        "upstream_repository":"JulioCacko/The-Order-1886_pc",
        "upstream_sha":UPSTREAM,
        "android_cpu_donor":"erickmendes22/gow3_android_daedalus_fork",
        "donor_sha":DONOR,
        "overlaid_files":FILES,
        "build_verified":False,
        "android_gameplay_verified":False,
    }
    (output/"ANDROID_PORT_MANIFEST.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf-8")
    print(f"Assembled {output}; {len(FILES)} modified/additional files. GPU/Android presentation not migrated yet.")

if __name__=="__main__":
    run()
