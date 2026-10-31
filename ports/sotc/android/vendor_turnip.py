#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Embed the exact GameHub-derived Turnip ZIP supplied by the user.

No recompilation/strip/patching of the driver is allowed. The archive is a
local optional vendor input, not fetched from an unverified third-party URL.
If absent, leave all existing Turnip paths and APK packaging functional.
"""
import hashlib
import json
from pathlib import Path
import struct
import zipfile

ARCHIVE_RELATIVE = "ports/sotc/android/vendor/turnip_gamehub_dd.zip"
ARCHIVE_SHA256 = "8255659cc205110e0fa89f2d364292b86fe563a2cedafbc41915bead5a611ecb"
LIB_SHA256 = "4f242a453496ab27fc29be950d632edbae494dcc0c9b7d56c37c7ebdffe42df9"


def embed_verified_turnip(stage: Path, archive: Path) -> bool:
    if not archive.is_file():
        print(f"SotC GameHub DD Turnip not bundled: optional binary missing ({archive})")
        print("The existing driver importer and bundled Gen8 fallback remain available.")
        return False
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Wrong GameHub/DD driver ZIP sha256; refusing bundle")
    with zipfile.ZipFile(archive) as zipped:
        if set(zipped.namelist()) != {"meta.json", "libvulkan_freedreno.so", "NOTICE.txt"}:
            raise ValueError("Unexpected GameHub/DD Turnip ZIP entries")
        meta = json.loads(zipped.read("meta.json"))
        so = zipped.read("libvulkan_freedreno.so")
        notice = zipped.read("NOTICE.txt")
    if (meta.get("schemaVersion") != 1 or meta.get("minApi") != 34 or
            meta.get("libraryName") != "libvulkan_freedreno.so"):
        raise ValueError("Wrong GameHub/DD Turnip package metadata")
    if (len(so) < 0x100 or so[:5] != b"\x7fELF\x02"
            or struct.unpack_from("<H", so, 18)[0] != 183
            or hashlib.sha256(so).hexdigest() != LIB_SHA256):
        raise ValueError("Wrong ARM64 GameHub/DD driver binary")
    base = stage / "sotcport" / "arm64" / "drivers" / "gamehub-dd"
    base.mkdir(parents=True, exist_ok=True)
    target = base / "libvulkan_freedreno.so"
    target.write_bytes(so)
    notice_dir = stage / "sotcport" / "licenses"
    notice_dir.mkdir(parents=True, exist_ok=True)
    (notice_dir / "NOTICE-GameHub-DD-Turnip.txt").write_bytes(notice)
    (base / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == LIB_SHA256
    print(f"Bundled exact user-tested GameHub/DD Turnip: {len(so)} bytes, sha256 {LIB_SHA256}")
    return True
