#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Allow bb-recomp to resolve PS4 x86-64 jump tables stored outside the function.

The upstream scanner assumes every relative-offset table sits inside its
owning function. SotC's clang-generated switch tables often live in a separate
read-only region: +0xf9f360 for the switch at +0x96d05 (5 cases). Restrict
DESTINATIONS to the function, but not the source bytes of the switch table.
This is a general decoder fix, not a list of game-address special cases.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = "    uint64_t stop = env.hi;\n"
PATCH = """    // Source bytes of the relative jump table need not be in [env.lo, env.hi).
    // clang keeps switch tables in .rodata; the PS4 game uses a RIP-relative
    // LEA to access them from the current executable function.
    // env.readS32 independently bounds each table read to the mapped image,
    // while target >= env.lo && target < env.hi validates *each destination*.
    // Keep the original stop for inline tables, and use the image read guard
    // for tables held in separate read-only segments. No unbounded read:
    // MaxEntries (4096) and the first invalid destination cap scanning.
    uint64_t stop = j.table >= env.lo && j.table < env.hi ? env.hi : UINT64_MAX;
"""

def patch(compiler_source: Path) -> Path:
    path=compiler_source/"src/jumptable.cpp"
    source=path.read_text(encoding="utf-8")
    if source.count(SOURCE)!=1:
        raise ValueError("Upstream jump-table stop condition differs; refusing unsafe patch")
    assert "constexpr uint32_t MaxEntries = 4096" in source
    assert "if (target < env.lo || target >= env.hi) break;" in source
    assert "if (!env.readS32(j.table + 4ull * e, v)) break;" in source
    path.write_text(source.replace(SOURCE,PATCH,1),encoding="utf-8")
    # Upstream caches --resume shards by BBR_COMPILER_VERSION, not by
    # executable SHA256. The former value "1" would silently REUSE object
    # files generated with the BROKEN switch decoder. Invalidate every shard
    # by bumping its compiler key; ABI stays 2.
    version=compiler_source/"src/version.h"
    old='#define BBR_COMPILER_VERSION "1"'
    ver=version.read_text(encoding="utf-8")
    if ver.count(old)!=1:
        raise ValueError("Pinned compiler version differs; refusing unsafe cache reuse")
    version.write_text(ver.replace(old,'#define BBR_COMPILER_VERSION "2"',1),encoding="utf-8")
    return path

def main()->None:
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("compiler_source",type=Path)
    args=cli.parse_args()
    print("SotC switch table decoder patched:",patch(args.compiler_source))

if __name__=="__main__":
    main()
