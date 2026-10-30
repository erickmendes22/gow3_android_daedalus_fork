#!/usr/bin/env python3
"""Detect missing SotC PC runtime HLE exports before building an Android APK."""
import argparse
from pathlib import Path
import re
import sys

parser=argparse.ArgumentParser()
parser.add_argument("--upstream",required=True,type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[3]
modules=("runtime_memory","runtime_sotc","runtime_kernel","runtime_content",
         "runtime_thread","runtime_mutex","runtime_services","runtime_file",
         "runtime_audio","runtime_sema","runtime_rwlock","runtime_savedata",
         "runtime_time","runtime_pad","runtime_ajm","runtime_rtc","runtime_fiber")
pattern=re.compile(r'\{\s*"(sce[A-Za-z0-9_]+)"\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}')
missing=[]
count=0
for module in modules:
    upstream=args.upstream/"src"/(module+".c")
    local=root/"src"/(module+".c")
    if not upstream.is_file() or not local.is_file():
        sys.exit(f"Missing source required for audit: {upstream} or {local}")
    original=set(pattern.findall(upstream.read_text()))
    ours={name for name,fn in pattern.findall(local.read_text())}
    for name,func in sorted(original):
        count+=1
        if name not in ours:
            missing.append((module,name,func))
if missing:
    for module,name,fn in missing:
        print(f"MISSING {module}: {name} ({fn})")
    sys.exit(f"SotC HLE export coverage FAILED: {len(missing)} missing of {count} original exports")
print(f"SotC runtime exported API coverage: {count} upstream API entries checked; 0 missing")
