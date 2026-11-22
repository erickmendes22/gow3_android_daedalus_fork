#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed test for native ARM64 CPU wait hint in SotC."""
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_sotc_cp_relax_arm64 import OLD, NEW, patch


class CpRelaxTests(unittest.TestCase):
    def sample(self):
        return (
            OLD + "\n" +
            "for (u32 spin = 0; spin < 4096; ++spin) { CpuRelax(); }\n" +
            "for (u32 spin = 0; back_tail.load(std::memory_order_acquire) < head; ++spin) {}\n" +
            "head - back_tail.load(std::memory_order_acquire) >= BackRingSize\n" +
            "back_head.store(head, std::memory_order_seq_cst)\n" +
            "back_tail.store(tail, std::memory_order_seq_cst)\n"
        )

    def test_aarch64_hint_without_queue_or_spin_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            f = Path(temp) / "shadps4/video_core/amdgpu/liverpool.cpp"
            f.parent.mkdir(parents=True)
            original = self.sample()
            f.write_text(original)
            patch(Path(temp))
            patched = f.read_text()
            self.assertEqual(patched, original.replace(OLD, NEW))
            self.assertIn('__asm__ __volatile__("yield" ::: "memory")', patched)
            self.assertIn("__builtin_ia32_pause()", patched)
            self.assertIn("4096", patched)
            with self.assertRaises(ValueError):
                patch(Path(temp))

    def test_missing_queue_guard_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            f = Path(temp) / "shadps4/video_core/amdgpu/liverpool.cpp"
            f.parent.mkdir(parents=True)
            f.write_text(OLD)
            with self.assertRaises(ValueError):
                patch(Path(temp))


if __name__ == "__main__":
    unittest.main()
