#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC CUSA08809 v01.00: verified Bachata S4+ 0.2.7 performance patches.

These are guest virtual addresses from the ORIGINAL decrypted PS4 SELF, NOT
byte offsets in eboot.bin. The native AjncSystem loader consumes BBPATCH2
with offsets relative to image base 0x400000.

Source: user-provided Bachata-S4-Plus-v0.2.7-QA.zip,
        patches/SotC_CUSA08809_Graphics.xml (author erickmendes22).
Validation source eboot SHA256: 21982727...e0b0a4e0 (65,314,052 bytes).

Never match by address alone. Reject foreign executables, unexpected original
instructions, occupied executable caves and any overlap with SotC native patches.
No permanent alteration of the user's game files.
"""
from pathlib import Path
import hashlib
import struct
import sys

BASE = 0x400000
EBOOT_SHA256 = "21982727c6f97fd415b3af5e99c5e071619c4dcc2248787a701a31a45ab0a4e0"
# entry: (code cave absolute guest address, injected bytes,
#         [(original call absolute guest address, original bytes, patched bytes)])
PATCHES = {
    "bloom": (0x0139a4f0, "488b4360c60000c6436800e9606808ff",
              [(0x004814fb, "e860f8f9ff", "e8f08ff100")]),
    "blur": (0x0139a510, "488b4360c60000c6436800e9406808ff",
             [(0x00483c8f, "e8ccd0f9ff", "e87c68f100")]),
    "ssr": (0x0139a550, "488b4360c60000c6436800e9006808ff",
            [(0x00475ecd, "e88eaefaff", "e87e46f200")]),
    "fog": (0x0139a570, "488b4360c60000c6436800e9e06708ff",
            [(0x0047afa0, "e8bb5dfaff", "e8cbf5f100")]),
    "shadows": (None, None, [
        (0x00474936, "e825c4faff", "e8f55bf200"),
        (0x00474468, "e8f3c8faff", "e82361f200"),
        (0x0047437c, "e8dfc9faff", "e82f62f200"),
        (0x0047819d, "e8be8bfaff", "e82e24f200"),
    ]),
}
SHADOW_CAVES = [
    (0x0139a530, "488b4360c60000c6436800e9206808ff"),
    (0x0139a590, "488b4360c60000c6436800e9c06708ff"),
    (0x0139a5b0, "488b4360c60000c6436800e9a06708ff"),
    (0x0139a5d0, "488b4360c60000c6436800e9806708ff"),
]


def parse_effects(value: str) -> tuple[str, ...]:
    names = tuple(dict.fromkeys(n.strip().lower() for n in value.split(",") if n.strip()))
    unknown = set(names) - PATCHES.keys()
    if unknown:
        raise ValueError("Unknown SotC Bachata performance patch: " + ", ".join(sorted(unknown)))
    return names


def _image_at(elf: bytes, ph: list, address: int, size: int, executable=True):
    va = address - BASE
    for segment in ph:
        if (segment["type"] in (1, 0x61000010)
                and segment["vaddr"] <= va
                and va + size <= segment["vaddr"] + segment["filesz"]
                and (not executable or segment["flags"] & 1)):
            file_off = segment["offset"] + va - segment["vaddr"]
            return bytes(elf[file_off:file_off + size])
    raise ValueError(f"Guest address {address:#x} is not mapped to executable code")


def _verify_calls(elf, ph, requested):
    writes = []
    for effect in requested:
        cave, code, calls = PATCHES[effect]
        cave_list = SHADOW_CAVES if effect == "shadows" else [(cave, code)]
        for address, hexcode in cave_list:
            code_bytes = bytes.fromhex(hexcode)
            if _image_at(elf, ph, address, len(code_bytes)) != bytes(len(code_bytes)):
                raise ValueError(f"SotC {effect}: code cave {address:#x} is occupied")
            writes.append((address - BASE, code_bytes))
        if len(cave_list) != len(calls):
            raise ValueError("SotC Bachata cave/call count mismatch")
        for i, (address, expected_hex, new_hex) in enumerate(calls):
            expected = bytes.fromhex(expected_hex)
            replacement = bytes.fromhex(new_hex)
            if len(expected) != len(replacement) or len(replacement) != 5 or replacement[0] != 0xE8:
                raise ValueError("Invalid SotC call patch length")
            if _image_at(elf, ph, address, len(expected)) != expected:
                raise ValueError(f"SotC {effect}: unexpected original bytes at {address:#x}")
            destination = address + 5 + struct.unpack("<i", replacement[1:])[0]
            if destination != cave_list[i][0]:
                raise ValueError(f"SotC {effect}: CALL points to {destination:#x}, expected {cave_list[i][0]:#x}")
            writes.append((address - BASE, replacement))
    spans = sorted((a, a + len(v)) for a, v in writes)
    if any(b > c for (_, b), (c, _) in zip(spans, spans[1:])):
        raise ValueError("Overlapping SotC Bachata performance writes")
    return writes


def append_bachata_patches(upstream: Path, eboot: Path, patch_file: Path,
                           title_id: str, effects: str) -> list[str]:
    requested = parse_effects(effects)
    if not requested:
        return []
    if title_id != "CUSA08809":
        raise ValueError("Bachata 0.2.7 native patches require CUSA08809 v01.00")
    source = eboot.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != EBOOT_SHA256:
        raise ValueError("Bachata 0.2.7 patches refused: SotC eboot SHA256 mismatch")
    # Pinned PC port parses PS4 SELF segment records and converts to ELF image.
    sys.path.insert(0, str(Path(upstream).resolve() / "scripts"))
    from prepare import parse_self
    elf, _, ph, _, _ = parse_self(source)
    writes = _verify_calls(elf, ph, requested)

    packed = patch_file.read_bytes()
    if len(packed) < 24:
        raise ValueError("Invalid native BBPATCH2 file")
    magic, base, count = struct.unpack_from("<8sQQ", packed)
    if magic != b"BBPATCH2" or base != BASE or count > 4096:
        raise ValueError("Unsupported native BBPATCH2 format/base")
    pos = 24
    existing = []
    for _ in range(count):
        if pos + 16 > len(packed):
            raise ValueError("Truncated native BBPATCH2 header")
        offset, length = struct.unpack_from("<QQ", packed, pos)
        pos += 16
        if length > len(packed) - pos:
            raise ValueError("Truncated native BBPATCH2 data")
        existing.append((offset, offset + length))
        pos += length
    if pos != len(packed):
        raise ValueError("Trailing native BBPATCH2 data")
    for address, payload in writes:
        if any(address < end and start < address + len(payload) for start, end in existing):
            raise ValueError(f"Bachata patch overlaps native SotC mode at {address + BASE:#x}")

    suffix = b"".join(struct.pack("<QQ", offset, len(data)) + data for offset, data in writes)
    updated = struct.pack("<8sQQ", magic, base, count + len(writes)) + packed[24:] + suffix
    temp = patch_file.with_name(patch_file.name + ".bachata.tmp")
    temp.write_bytes(updated)
    temp.replace(patch_file)
    print(f"SotC Bachata S4+ 0.2.7: {','.join(requested)}, "
          f"{len(writes)} verified writes, original eboot SHA256={digest}")
    return list(requested)
