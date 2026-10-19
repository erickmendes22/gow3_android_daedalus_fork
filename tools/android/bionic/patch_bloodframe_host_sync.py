#!/usr/bin/env python3
"""Patch the pinned MIT Bloodframe Android wrapper for a genuine host-sync route.

The original bb_lsfg_present always exports SYNC_FD, even when the caller has
already synchronized input on the CPU. Turnip Gen8 can fault on that GPU route
during the warm-up (generation_count=0). The in_sem_fd=-2 sentinel is private
to this GOW3-specific wrapper, not the public Bloodframe API.
"""
import sys
from pathlib import Path

src = Path(sys.argv[1]) if len(sys.argv) == 2 else None
if src is None or not src.is_file():
    raise SystemExit("Pass the path to the pinned bloodframe/android/bb_lsfg.cpp")

source = src.read_text(encoding="utf-8")
marker = "GOW3_BIONIC_HOST_SYNC_NO_EXTERNAL_FD"
if marker in source:
    print("Bloodframe: already patched for native host-sync")
    raise SystemExit(0)

needle = """        // The input semaphore is a sync file (or -1, already signaled); the framegen imports it.
        constexpr auto handle_type = VK_EXTERNAL_SEMAPHORE_HANDLE_TYPE_SYNC_FD_BIT;
        const LSFG::AndroidFrameSyncFds sync =
"""
replacement = """        // The input semaphore is a sync file (or -1, already signaled); the framegen imports it.
        constexpr auto handle_type = VK_EXTERNAL_SEMAPHORE_HANDLE_TYPE_SYNC_FD_BIT;
        // GOW3_BIONIC_HOST_SYNC_NO_EXTERNAL_FD: input was CPU-synchronized by
        // the game device. -2 means NO semaphore; -1 would import a synthetic
        // already-signaled SYNC_FD on Turnip. Crucially this also avoids
        // exporting a SYNC_FD from the framegen device during warm-up.
        if (in_sem_fd == -2) {
            const std::vector<int> no_external_outputs;
            if (g_performance) {
                LSFG_3_1P::presentContextWithCount(ctx, -2, no_external_outputs,
                                                  count, handle_type);
            } else {
                LSFG_3_1::presentContextWithCount(ctx, -2, no_external_outputs,
                                                 count, handle_type);
            }
            out->gpu_synced = 0; // The host calls bb_lsfg_wait before sampling outputs.
            return 0;
        }
        const LSFG::AndroidFrameSyncFds sync =
"""
if source.count(needle) != 1:
    raise SystemExit("Pinned Bloodframe source changed; refusing an unsafe patch")
src.write_text(source.replace(needle, replacement, 1), encoding="utf-8")
print("Bloodframe: enabled GOW3 host-sync mode without any external SYNC_FD")
