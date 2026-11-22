#!/usr/bin/env python3
"""Embed SotC launch options into a dedicated RW guest segment BEFORE AOT compilation.

The FEX launcher used --sotc-cmdline to patch a RIP-relative LEA at runtime.
AOT cannot support that late change: code must be compiled from exact runtime
bytes. Instead add a mapped 16-KiB data region and prepatch the LEA, then run
the same prepared image without --patches or --sotc-cmdline.
"""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import struct

HDR=struct.Struct("<8s12Q")
SEG=struct.Struct("<QQQ")
CMD=struct.Struct("<8sQ")
CMD_CAP=16384

def round_page(n:int)->int:
    return (n+16383)&~16383  # 16-KiB Android kernels require segment start alignment

def header_info(raw:bytes):
    if len(raw)<HDR.size:
        raise ValueError("BBPROBE5 truncated")
    fields=list(HDR.unpack_from(raw))
    if fields[0]!=b"BBPROBE5":
        raise ValueError("BBPROBE5 signature missing")
    size,nseg,nrel,nimp,nmods=fields[1],fields[3],fields[4],fields[5],fields[12]
    if not (0<size<512*1024*1024 and 0<nseg<33 and 0<=nmods<17
            and nrel<4000000 and nimp<100000):
        raise ValueError("BBPROBE5 header out of range")
    binds_at=HDR.size+56*nmods
    if binds_at+8>len(raw):
        raise ValueError("BBPROBE5 bindings missing")
    binds=struct.unpack_from("<Q",raw,binds_at)[0]
    if binds>100000:
        raise ValueError("BBPROBE5 binding count invalid")
    seg_at=binds_at+8+24*binds
    table_end=seg_at+24*nseg+128*nimp+32*nrel
    if len(raw)!=table_end+size:
        raise ValueError("BBPROBE5 image/table length mismatch")
    segs=[SEG.unpack_from(raw,seg_at+24*i) for i in range(nseg)]
    return fields,seg_at,segs,table_end

def embed(boot:Path,cmdline:Path,dest:Path)->dict:
    if boot.resolve()==dest.resolve():
        raise ValueError("never overwrite the original prepared guest image")
    old=boot.read_bytes()
    fields,seg_at,segs,table_end=header_info(old)
    cmd=cmdline.read_bytes()
    if len(cmd)<=CMD.size:
        raise ValueError("SOTCCMD1 truncated")
    magic,lea=CMD.unpack_from(cmd)
    text=cmd[CMD.size:]
    if magic!=b"SOTCCMD1" or not text or b"\x00" in text or len(text)+1>CMD_CAP:
        raise ValueError("invalid SotC engine command line")
    image=bytearray(old[table_end:])
    if lea+7>len(image) or image[lea:lea+3]!=b"\x48\x8d\x35":
        raise ValueError("SotC LEA signature mismatch; refuse to patch x86")
    start=round_page(len(image))
    if any(start<off+length and off<start+CMD_CAP for off,length,_ in segs):
        raise ValueError("new guest data segment overlaps a mapped segment")
    displacement=start-(lea+7)
    if not -(1<<31)<=displacement<1<<31:
        raise ValueError("RIP-relative displacement outside signed 32-bit range")
    # Match original x86 48 8d 35 disp32. LLVM then relocates the pointer.
    struct.pack_into("<i",image,lea+3,displacement)
    image.extend(b"\x00"*(start-len(image)))
    image.extend(text+b"\x00")
    image.extend(b"\x00"*(CMD_CAP-len(text)-1))
    fields[1]=len(image)
    fields[3]=len(segs)+1
    table=bytearray(old[:table_end])
    table[:HDR.size]=HDR.pack(*fields)
    table[seg_at+24*len(segs):seg_at+24*len(segs)]=SEG.pack(start,CMD_CAP,6)
    full=bytes(table)+image
    check,_,segments,new_end=header_info(full)
    if check[1]!=start+CMD_CAP or len(segments)!=len(segs)+1 or new_end!=len(table):
        raise ValueError("prelinked AOT image failed structure validation")
    if full[new_end+start:new_end+start+len(text)+1]!=text+b"\x00":
        raise ValueError("engine command line data not preserved")
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_name(dest.name+".tmp")
    try:
        with tmp.open("wb") as f:
            f.write(full)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dict(lea=hex(lea),cmdline_bytes=len(text),segment_start=hex(start),
                segment_size=CMD_CAP,segment_count=len(segments),image_bytes=len(image),
                cmdline_sha256=hashlib.sha256(cmd).hexdigest(),
                native_boot_sha256=hashlib.sha256(full).hexdigest())

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--boot",type=Path,required=True)
    p.add_argument("--cmdline",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    print(embed(a.boot,a.cmdline,a.out))

if __name__=="__main__":
    main()
