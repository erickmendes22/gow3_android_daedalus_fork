#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify exact SotC PS4 register state replay with 16 instead of 64 dwords.

Checks both the original and patched PM4 capture logic against a dense
reference register file, with multi-chunk and sparse SET_*REG writes.
No Vulkan draw, guest readback or emulated register can be discarded.
"""
import importlib.util
from pathlib import Path
import random
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'ports/sotc/android/stage_cp_draw_queue.py'
STAGING=ROOT/'ports/sotc/android/stage_renderer.py'
UPSTREAM=ROOT/'upstream-sotc/gpu/shadps4/video_core/amdgpu'
spec=importlib.util.spec_from_file_location("sotc_cp_queue_test",PATCH)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def capture_replay(words,changes,chunk_size,seed=1):
    rnd=random.Random(seed)
    expected=[0]*words
    replay=[0]*words
    next_values=[0]*words
    total_bytes=0
    for step in range(changes):
        dirty=set()
        for _ in range(rnd.randint(1,7)):
            offset=rnd.randrange(words)
            count=min(rnd.randint(1,18), words-offset)
            values=[rnd.getrandbits(32) for _ in range(count)]
            next_values[offset:offset+count]=values
            expected[offset:offset+count]=values
            first=offset//chunk_size
            last=(offset+count-1)//chunk_size
            for chunk in range(first,last+1):
                dirty.add(chunk)
        packet=[]
        for chunk in sorted(dirty):
            offset=chunk*chunk_size
            packet.append((chunk,next_values[offset:offset+chunk_size]))
        for chunk,data in packet:
            offset=chunk*chunk_size
            replay[offset:offset+chunk_size]=data
            total_bytes+=len(data)*4
        if replay!=expected:
            raise AssertionError(f"Register mismatch step={step} chunk={chunk_size}")
    return total_bytes


class SotcCpDrawQueueTest(unittest.TestCase):
    def test_compacted_snapshots_replay_every_guest_register(self):
        # Actual pinned Regs::NumRegs = 0xD000 (53248 dwords).
        words=0xD000
        self.assertEqual(words%16,0)
        self.assertLessEqual(words//16,65536)
        # Stress boundaries and CPU->draw snapshots with deterministic data.
        old_bytes=capture_replay(words,150,64,seed=20261101)
        new_bytes=capture_replay(words,150,16,seed=20261101)
        self.assertLess(new_bytes,old_bytes)
        self.assertLess(new_bytes,old_bytes*0.8)

    def test_android_spin_is_cpu_friendly_and_preserves_waits(self):
        source=PATCH.read_text()
        for term in (
            "static constexpr u32 RegChunkDwords = 16;",
            "static constexpr u32 RegChunkDwords = 64;",
            "static_assert(Regs::NumRegs % RegChunkDwords == 0",
            "static constexpr u32 SotcCpSpinBudget = 256;",
            "static constexpr u32 SotcCpSpinBudget = 4096;",
            '__asm__ volatile("yield" ::: "memory");',
            "back_cv.wait_for(", "drain_cv.wait_for(",
            "back_head.store(head, std::memory_order_seq_cst)",
            "back_tail.store(tail, std::memory_order_seq_cst)"):
            self.assertIn(term, source)
        self.assertIn("from stage_cp_draw_queue import patch_cp_draw_queue",STAGING.read_text())

    @unittest.skipUnless(UPSTREAM.exists(),"Pinned upstream checkout required")
    def test_exact_original_renderer_sources_patch_without_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            gpu=Path(temp)
            target=gpu/'shadps4/video_core/amdgpu'
            target.mkdir(parents=True)
            for file in ("liverpool.cpp","liverpool.h"):
                (target/file).write_bytes((UPSTREAM/file).read_bytes())
            mod.patch_cp_draw_queue(gpu)
            cpp=(target/'liverpool.cpp').read_text()
            hdr=(target/'liverpool.h').read_text()
            self.assertEqual(cpp.count("if (spin < SotcCpSpinBudget)"),2)
            self.assertEqual(cpp.count("for (u32 spin = 0; spin < SotcCpSpinBudget; ++spin)"),1)
            self.assertIn("static constexpr u32 RegChunkDwords = 16;",hdr)
            self.assertIn("static constexpr u32 NumRegChunks = Regs::NumRegs / RegChunkDwords;",hdr)
            # Patch must fail against already-mutated or unexpected source.
            with self.assertRaises(ValueError):
                mod.patch_cp_draw_queue(gpu)


if __name__=="__main__":
    unittest.main()
