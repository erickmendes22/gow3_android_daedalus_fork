#!/usr/bin/env python3
"""Refuse a stale on-device SotC ARM64 AOT library after patch/game changes."""
import argparse
import hashlib
import json
from pathlib import Path

def hash_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):
            h.update(block)
    return h.hexdigest()

def valid(prepared:Path,report_file:Path)->bool:
    if not report_file.is_file():return False
    report=json.loads(report_file.read_text())
    if report.get("status")!="aot_library_built_not_executed": return False
    if report.get("tso")!="disabled" or report.get("game",{}).get("title_id") not in ("CUSA08809","CUSA08034"):
        return False
    image=report.get("image",{})
    coverage=report.get("coverage",{})
    if image.get("patch_sha256")!=hash_file(prepared/"patches.bin"):return False
    if report.get("original_boot_sha256")!=hash_file(prepared/"boot-linked.bin"):return False
    if report.get("cmdline_sha256")!=hash_file(prepared/"cmdline.bin"):return False
    # Runtime MUST start the exact same image that the AOT compiler read.
    boot=report_file.parent/"boot-native.bin"
    if not boot.is_file() or report.get("aot_boot_sha256")!=hash_file(boot):
        return False
    if "cmdline" not in report or report["cmdline"].get("segment_count",0)<10:
        return False
    so=report_file.parent/"libSotcAot.so"
    return so.is_file() and coverage.get("library_sha256")==hash_file(so)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prepared",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    try:
        if valid(a.prepared,a.report):return 0
    except (OSError,ValueError,KeyError,TypeError):
        pass
    print("AOT game image or patches changed; use Build AOT before starting game.",flush=True)
    return 1
if __name__=="__main__":
    raise SystemExit(main())
