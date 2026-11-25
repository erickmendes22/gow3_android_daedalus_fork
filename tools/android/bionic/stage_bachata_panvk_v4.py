#!/usr/bin/env python3
"""Extract the original, unmodified PanVK package from the SHA-pinned Bachata APK.
Never rename a different release or synthesize driver metadata.
"""
import hashlib
import io
import json
import pathlib
import struct
import subprocess
import tempfile
import zipfile

URL = "https://github.com/JICA98/Bachata-S4/releases/download/v0.2.6/bachatas4-0.2.6-release.apk"
APK_SHA = "39d38d4e781bc83ee2542b3884a264895e726c3c8ee49df493ded487e6cd6f74"
DEST = pathlib.Path("out/android-release/assets/drivers/Bachata-PanVK-V4-0.2.6.zip")

def find_driver(apk):
    candidates = {}
    with zipfile.ZipFile(apk) as outer:
        for entry in outer.infolist():
            name = entry.filename.lower()
            if not name.endswith((".zip", ".adpkg")) or not 1024 < entry.file_size <= 256*1024*1024:
                continue
            # A genuine driver package must include its own metadata and ARM64 ELF.
            data = outer.read(entry)
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as inner:
                    if "meta.json" not in inner.namelist():
                        continue
                    meta = json.loads(inner.read("meta.json"))
                    library = meta.get("libraryName", "")
                    identity = (name + " " + json.dumps(meta)).lower()
                    if "panvk" not in identity and "panfrost" not in library.lower():
                        continue
                    if any(x in identity for x in ("v3.2", "v3 3.2", "2a9358a", "bachata v3")):
                        continue
                    if not isinstance(library,str) or library.startswith("/") or ".." in pathlib.PurePosixPath(library).parts:
                        continue
                    if library not in inner.namelist() or int(meta.get("minApi",35))>35:
                        continue
                    if meta.get("schemaVersion",1)!=1:
                        continue
                    with inner.open(library) as elf:
                        head=elf.read(64)
                    if len(head)<20 or head[:6]!=b"\x7fELF\x02\x01" or struct.unpack_from("<H",head,18)[0]!=183:
                        continue
                    # V4 release describes native layouts + v11 robust SSBO changes.
                    # Only select the PanVK package shipped by that exact APK.
                    candidates[hashlib.sha256(data).hexdigest()]=(entry.filename,data)
            except (ValueError,KeyError,TypeError,zipfile.BadZipFile):
                continue
    if len(candidates)!=1:
        raise RuntimeError(f"Expected one eligible PanVK package in pinned 0.2.6 APK, found {list(candidates)}")
    sha,(name,data)=next(iter(candidates.items()))
    return sha,name,data

def main():
    DEST.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        apk=pathlib.Path(temp)/"bachata.apk"
        subprocess.run(["curl","-fLsS","--retry","3","--connect-timeout","30","-o",str(apk),URL],check=True)
        with apk.open("rb") as f:
            if hashlib.file_digest(f,"sha256").hexdigest()!=APK_SHA:
                raise RuntimeError("Bachata APK SHA256 mismatch")
        sha,name,data=find_driver(apk)
        DEST.write_bytes(data)
        DEST.with_name(DEST.name+".sha256").write_text(sha+"\n",encoding="ascii")
        print(f"PanVK package from verified Bachata v0.2.6: {name}; SHA256 {sha}")

if __name__=="__main__":
    main()
