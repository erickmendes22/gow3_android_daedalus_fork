#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC 0.1.68: prevent v0.1.67's unresolved runtime_memory_clamp_gap_hits boot failure."""
from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "ports/sotc/android/verify_sotc_link.py"
spec = importlib.util.spec_from_file_location("verify_sotc_link", VALIDATOR)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class SotcAndroidHostAbiTests(unittest.TestCase):
    def test_counter_has_real_atomic_semantics_and_correct_c_abi(self):
        s = (ROOT / "src/runtime_memory.c").read_text()
        self.assertIn("uint64_t runtime_memory_clamp_gap_hits(void)", s)
        self.assertIn("__atomic_exchange_n(&clamp_gap_hits, 0, __ATOMIC_RELAXED)", s)
        self.assertIn("__atomic_fetch_add(&clamp_gap_hits, 1, __ATOMIC_RELAXED)", s)
        self.assertIn("if (size && sotc_vm_unmapped_fast(address))", s)

    def test_dynamic_abi_checker_catches_the_exact_067_failure(self):
        undef = checker.dynamic_symbols(
            "                 U runtime_memory_clamp\n"
            "                 U runtime_memory_clamp_gap_hits\n"
            "                 w runtime_pool_release_dump\n", False)
        host = checker.dynamic_symbols(
            "0000000000315f2c T runtime_memory_clamp\n"
            "00000000003138c0 T runtime_process_time_us\n", True)
        missing = {s for s in undef if s.startswith("runtime_") and s not in host}
        self.assertEqual(missing, {"runtime_memory_clamp_gap_hits"})
        host.add("runtime_memory_clamp_gap_hits")
        self.assertFalse({s for s in undef if s.startswith("runtime_") and s not in host})

    def test_early_and_final_elf_linker_gates_are_in_build(self):
        workflow = (ROOT / ".github/workflows/sotc-aot-068-apk.yml").read_text()
        self.assertIn("VERIFY GPU-to-host ELF runtime ABI before packaging (fatal)", workflow)
        self.assertEqual(workflow.count("python3 ports/sotc/android/verify_sotc_link.py"), 2)
        self.assertIn("--probe out/bionic/bin/gow3-probe", workflow)
        self.assertIn("sotcport/arm64/bin/sotc-probe > \"$RUNNER_TEMP/sotc-final-probe\"", workflow)
        self.assertIn('--probe "$RUNNER_TEMP/sotc-final-probe"', workflow)
        self.assertIn("run-id: 45069117755", workflow)  # Reuse already validated renderer.
        self.assertIn("versionCode = 10069", (ROOT / "android-launcher/app/build.gradle.kts").read_text())


if __name__ == "__main__":
    unittest.main()
