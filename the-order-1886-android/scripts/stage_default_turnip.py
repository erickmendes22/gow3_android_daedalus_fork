#!/usr/bin/env python3
"""Make a pinned GameHub Turnip release installable by the Android AdrenoTools driver store.

The release comes from the user's WinlatorComponents GitHub release. CI downloads
and SHA-256-verifies it; game files and vendor binaries are never committed here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import struct
import zipfile

RELEASE_SHA256 = "8255659cc205110e0fa89f2d364292b86fe563a2cedafbc41915bead5a611ecb"
DRIVER_NAME = "GameHub Turnip 26.3 + DD GMEM + PWR_MAX (Experimental)"


def arm64_elf(data):
    return (len(data) >= 64 and data[:6] == b"\x7fELF\x02\x01"
            and struct.unpack_from("<H", data, 16)[0] == 3
            and struct.unpack_from("<H", data, 18)[0] == 183)


def stage(source, destination):
    payload = source.read_bytes()
    if len(payload) > 32 * 1024 * 1024:
        raise ValueError("Unexpectedly large Turnip archive")
    sha = hashlib.sha256(payload).hexdigest()
    if sha != RELEASE_SHA256:
        raise ValueError(f"Turnip release SHA-256 mismatch: {sha}")
    libraries = {}
    with zipfile.ZipFile(source) as package:
        entries = package.infolist()
        if len(entries) > 256 or sum(max(0, e.file_size) for e in entries) > 100 * 1024 * 1024:
            raise ValueError("Turnip ZIP exceeds entry/size limits")
        for entry in entries:
            if entry.is_dir() or not entry.filename.lower().endswith(".so"):
                continue
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename:
                raise ValueError("Unsafe driver entry path")
            data = package.read(entry)
            if not arm64_elf(data):
                continue
            name = path.name
            if name in libraries and libraries[name] != data:
                raise ValueError("Conflicting ARM64 libraries named " + name)
            libraries[name] = data
    if not libraries:
        raise ValueError("Release has no Android ARM64 ELF shared libraries")
    names = ("libvulkan_freedreno.so", "vulkan.adreno.so",
             "libvulkan_adreno.so", "libvulkan_turnip.so")
    selected = next((n for n in names if n in libraries), None)
    if selected is None:
        possible = [n for n in libraries if "vulkan" in n.lower()]
        if len(possible) != 1:
            raise ValueError("Cannot identify unambiguous Vulkan driver: " + str(sorted(libraries)))
        selected = possible[0]
    meta = {"schemaVersion": 1, "name": DRIVER_NAME, "libraryName": selected, "minApi": 30}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        out.writestr("meta.json", json.dumps(meta, ensure_ascii=False, sort_keys=True))
        for name, data in sorted(libraries.items()):
            out.writestr(name, data)
    os.replace(temp, destination)
    with zipfile.ZipFile(destination) as out:
        assert json.loads(out.read("meta.json"))["libraryName"] == selected
        assert arm64_elf(out.read(selected))
    print("Pinned release SHA-256:", sha)
    print("Selected Vulkan ELF:", selected)
    print("Included ARM64 libraries:", sorted(libraries))
    print("Asset:", destination, destination.stat().st_size, "bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    stage(args.source, args.destination)
