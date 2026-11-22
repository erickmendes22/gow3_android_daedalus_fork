#!/usr/bin/env python3
"""Stage the pinned official bb-recomp Android compiler into the SotC payload.

Only a toolchain is installed: no game data or compiler runs in GitHub Actions.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import tarfile

VERSION = "v1.3.0"
DIGEST = "e0598aebe5b148419d06484e2f02aa19a2a2743915cfdd87a45da814f34d0681"

def stage(archive: Path, root: Path) -> dict:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != DIGEST:
        raise ValueError("Wrong official Android AOT compiler archive (SHA256 mismatch)")
    tool = root / "arm64/aot"
    tool.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:xz") as t:
        for member in t.getmembers():
            if not member.isfile():
                continue
            # Never allow path traversal or symlinks from a remote archive.
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise ValueError("Unsafe compiler archive")
        name = next((m for m in t.getmembers() if m.isfile() and
                     m.name.endswith("/libbbrecomp.so")), None)
        bundles = [m for m in t.getmembers() if m.isfile() and
                   "/bundle/" in ("/"+m.name)]
        if not name or not bundles:
            raise ValueError("Archive lacks executable libbbrecomp.so or LLVM bundle")
        with t.extractfile(name) as source:
            target = tool/"bin/libbbrecomp.so"
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as output: shutil.copyfileobj(source, output)
        if target.read_bytes()[:4] != b"\x7fELF":
            raise ValueError("Official Android AOT compiler does not contain an ELF")
        with target.open("rb") as f:
            f.seek(18)
            if int.from_bytes(f.read(2), "little") != 183:
                raise ValueError("Official AOT compiler must be ARM64 ELF")
        os.chmod(target, 0o755)
        for m in bundles:
            suffix = m.name.split("/bundle/", 1)[1]
            if not suffix or ".." in Path(suffix).parts:
                raise ValueError("Unsafe LLVM bundle member")
            dest = tool / "bundle" / suffix
            dest.parent.mkdir(parents=True, exist_ok=True)
            with t.extractfile(m) as inp, dest.open("wb") as out:
                shutil.copyfileobj(inp, out)
            if m.mode & 0o111:
                os.chmod(dest, 0o755)
        for m in t.getmembers():
            if not m.isfile() or not (m.name.endswith("/LICENSE") or "/licenses/" in m.name):
                continue
            basename=Path(m.name).name
            dest=tool/"licenses"/basename
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                with t.extractfile(m) as inp, dest.open("wb") as out:
                    shutil.copyfileobj(inp,out)
    (tool/"upstream.sha256").write_text(DIGEST+"\n")
    return {"version":VERSION,"sha256":DIGEST,"compiler_size":target.stat().st_size,
            "bundle_files":len(bundles)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--runtime",type=Path,required=True)
    a=p.parse_args()
    print(stage(a.archive,a.runtime))

if __name__=="__main__":
    main()
