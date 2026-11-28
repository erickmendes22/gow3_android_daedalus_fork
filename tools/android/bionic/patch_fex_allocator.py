#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Apply the Android VA-probe fix to the pinned FEX source before NDK compilation.
Keep the upstream submodule commit unchanged. Refuse unexpected source layout.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BEGIN = "FEX_DEFAULT_VISIBILITY size_t GetHostVABits() {"
END = "\n#define STEAL_LOG"
INCLUDE = '#include "gow3_android_va_probe.h"'
REPLACEMENT = r'''FEX_DEFAULT_VISIBILITY size_t GetHostVABits() {
  static const size_t HostVABits = []() -> size_t {
    const long PageSize = sysconf(_SC_PAGESIZE);
    if (PageSize <= 0) {
      std::fprintf(stderr, "UB2_FEX_VA failed=page-size\n");
      _exit(21);
    }
    const auto Result = Gow3FexVa::Probe(static_cast<size_t>(PageSize),
      [](uintptr_t Address, size_t Size) {
        void* Ptr = ::mmap(reinterpret_cast<void*>(Address), Size, PROT_NONE,
                           MAP_FIXED_NOREPLACE | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        // Capture errno BEFORE munmap or any other library call.
        const int Error = Ptr == MAP_FAILED ? errno : 0;
        return Gow3FexVa::Mapping{reinterpret_cast<uintptr_t>(Ptr), Error, Ptr != MAP_FAILED};
      },
      [](uintptr_t Address, size_t Size) {
        if (::munmap(reinterpret_cast<void*>(Address), Size) != 0) {
          std::fprintf(stderr, "UB2_FEX_VA failed=unmap errno=%d\n", errno);
          _exit(21);
        }
      });
    std::fprintf(stderr, "UB2_FEX_VA bits=%zu page=%ld relocated=%u high48=%d\n",
                 Result.bits, PageSize, Result.relocated, int(Result.bits >= 48));
    if (!Result.bits) {
      // Do not guess at host VA width or reach compiler UB in release.
      std::fprintf(stderr, "UB2_FEX_VA failed=no-verified-width\n");
      _exit(21);
    }
    return Result.bits;
  }();
  return HostVABits;
}
'''

def apply(fex):
    source = Path(fex) / "FEXCore/Source/Utils/Allocator.cpp"
    original = source.read_text()
    if original.count(BEGIN) != 1 or original.count(END) != 1:
        raise RuntimeError("Unexpected pinned FEX VA probe source")
    start = original.index(BEGIN)
    end = original.index(END, start)
    if INCLUDE in original:
        if original[start:end].strip() != REPLACEMENT.strip():
            raise RuntimeError("Existing Android VA probe patch differs")
        patched = original
    else:
        old = original[start:end]
        if "if (Ptr != (void*)~0ULL || errno == EEXIST)" not in old or "MAP_FIXED_NOREPLACE" not in old:
            raise RuntimeError("Unexpected upstream VA detection; review before building")
        anchor = '#include "Utils/Allocator.h"'
        if original.count(anchor) != 1:
            raise RuntimeError("Unexpected FEX allocator include layout")
        patched = (original[:start] + REPLACEMENT + original[end:]).replace(anchor, anchor + "\n" + INCLUDE)
    header = ROOT / "cpu/fex_android_va_probe.h"
    (source.parent / "gow3_android_va_probe.h").write_bytes(header.read_bytes())
    source.write_text(patched)
    print("FEX Android VA probe: exact mmap address, actual page size, legacy fallback")

if __name__ == "__main__":
    apply(sys.argv[1])
