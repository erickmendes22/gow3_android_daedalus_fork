#!/usr/bin/env python3
"""Fail closed when a SotC AOT CPU backend needs C++ symbols absent from the runtime.

The CPU engine and shipped C++ ABI must match; the old runtime's public C++
symbols must remain available to the native renderer and existing bridges.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

def symbols(path: Path, readelf: str = "readelf") -> tuple[set[str],set[str]]:
    output=subprocess.check_output([readelf,"--dyn-syms","--wide",str(path)],text=True)
    defined=set();undefined=set()
    for line in output.splitlines():
        fields=line.split()
        if len(fields)<8 or not fields[0].endswith(":") or not fields[0][:-1].isdigit():
            continue
        symbol=fields[7].split("@",1)[0]
        if fields[6]=="UND":
            undefined.add(symbol)
        elif fields[4] in ("GLOBAL","WEAK") and fields[5]!="HIDDEN":
            defined.add(symbol)
    return defined,undefined

def verify(old: Path, new: Path, cpu: Path, readelf: str = "readelf") -> dict:
    previous,_=symbols(old,readelf)
    candidate,_=symbols(new,readelf)
    _,required=symbols(cpu,readelf)
    removed=previous-candidate
    missing={n for n in required if n.startswith("_ZNSt6__ndk1")} - candidate
    missing_before={n for n in required if n.startswith("_ZNSt6__ndk1")} - previous
    if removed:
        raise ValueError(f"New libc++ removes {len(removed)} old ABI symbols: {sorted(removed)[:8]}")
    if missing:
        raise ValueError(f"CPU requires {len(missing)} absent libc++ symbols: {sorted(missing)[:8]}")
    if "_ZNSt6__ndk113__hash_memoryEPKvm" not in candidate:
        raise ValueError("AOT CPU requires std::__ndk1::__hash_memory not exported by libc++")
    return dict(old_exports=len(previous),new_exports=len(candidate),
                cpu_symbols_fixed=sorted(missing_before),old_exports_removed=0)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old",type=Path,required=True)
    p.add_argument("--new",type=Path,required=True)
    p.add_argument("--cpu",type=Path,required=True)
    p.add_argument("--readelf",default="readelf")
    a=p.parse_args()
    print(verify(a.old,a.new,a.cpu,a.readelf))
if __name__=="__main__":
    main()
