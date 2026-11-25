#!/usr/bin/env python3
"""Stage unmodified, SHA-pinned driver releases from the PistonPort PanVK hub.
Never mix libraries from different Vulkan ICDs. Retain source attribution.
"""
import hashlib
import json
import pathlib
import struct
import subprocess
import tempfile
import zipfile

DEST = pathlib.Path("out/android-release/assets/drivers")
DRIVERS = [
    {
        "id": "panvk-minegraph8",
        "name": "MineGraph PanVK 26.3.0 panvk.8",
        "file": "Mesa.26.3.0-panvk.8.zip",
        "sha": "e71e23cdd2ddf52f72d7c348b5754df323cd56fbe6e0087b4c5c9b116565be4b",
        "url": "https://github.com/MineGraph-bilibili/panvk-Android/releases/download/Mesa.26.3.0-panvk.8/Mesa.26.3.0-panvk.8.zip"
    },
    {
        "id": "panvk-jim-r10",
        "name": "JimVulkan PanVK Mesa 27 R10",
        "file": "mali-panvk-27.0.0-devel-r10.zip",
        "sha": "7e97db4d79d81ec9461d1e0676b62a865561cb56e21c151693aa25ffbe749f1c",
        "url": "https://github.com/JimVulkan/mali-panvk/releases/download/v1.6.0/mali-panvk-27.0.0-devel-r10.zip"
    }
]

def validate(path, expected):
    with path.open("rb") as stream:
        if hashlib.file_digest(stream,"sha256").hexdigest()!=expected:
            raise ValueError("Driver release SHA-256 mismatch")
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if names.count("meta.json")!=1 or names.count("libvulkan_panfrost.so")!=1:
            raise ValueError("Missing or ambiguous Vulkan ICD package")
        meta=json.loads(archive.read("meta.json"))
        if meta.get("libraryName")!="libvulkan_panfrost.so" or int(meta.get("minApi",35))>35:
            raise ValueError("Unexpected driver metadata")
        if meta.get("schemaVersion",1)!=1:
            raise ValueError("Unsupported driver schema")
        with archive.open("libvulkan_panfrost.so") as f:
            head=f.read(64)
        if len(head)!=64 or head[:6]!=b"\x7fELF\x02\x01" or struct.unpack_from("<HH",head,16)!=(3,183):
            raise ValueError("Not an ARM64 shared library")
        for name in names:
            p=pathlib.PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name:
                raise ValueError("Invalid ZIP path")

def stage():
    DEST.mkdir(parents=True,exist_ok=True)
    for d in DRIVERS:
        final=DEST/d["file"]
        with tempfile.TemporaryDirectory(dir=DEST) as temp:
            path=pathlib.Path(temp)/d["file"]
            subprocess.run(["curl","-fLsS","--retry","3","--connect-timeout","30","-o",str(path),d["url"]],check=True)
            validate(path,d["sha"])
            path.replace(final)
        print(f"Staged {d['name']} SHA256={d['sha']}")
    (DEST/"mali-performance-drivers.json").write_text(json.dumps(DRIVERS,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    stage()
