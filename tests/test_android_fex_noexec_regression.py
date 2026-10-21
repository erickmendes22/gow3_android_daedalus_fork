"""2.1.7 crash regression from real 2026-10-20 Android traces.

Both reports have NoExec BE71D6713F11AA45: a run with all seven cheats
enabled and a run with all seven disabled. Before this fix all 8 cheat sites
and all 5 QTE sites were still installed in the OFF run. These checks verify
that the OFF path does NOT install hooks, while preserving code for ON runs.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = (ROOT / "src/probe.c").read_text(encoding="utf-8")
HELPER = (ROOT / "src/fex_guest_hook.h").read_text(encoding="utf-8")

def body_between(start, end):
    a = PROBE.index(start)
    z = PROBE.index(end, a)
    return PROBE[a:z]

class FexNoExecRegression(unittest.TestCase):
    def test_all_disabled_cheats_install_no_guest_syscalls(self):
        body = body_between("static void install_cheats_fex(", "\n#endif")
        guard = body.index('if (!flag || !*(volatile const unsigned char *)flag)')
        hook = body.index("guest_cpu_hook(address, hook->length, gow3_fex_cheat_callback)")
        self.assertLess(guard, hook)
        self.assertIn('printf("FEX Cheats: %s OFF - no guest code patched', body)
        self.assertIn("continue;", body[guard:body.index("int valid = 1;", guard)])
        self.assertIn("gow3_cheat_flag(id)", body)

    def test_disabled_auto_qte_has_no_guest_syscalls(self):
        body = body_between("static void install_auto_qte_fex(", "\n#endif")
        guard = body.index('if (!automatic || !*(volatile const unsigned char *)automatic)')
        hook = body.index("guest_cpu_hook(address, lengths[i], gow3_fex_qte_callback)")
        self.assertLess(guard, body.index("allocate(page_size)", guard))
        self.assertLess(guard, hook)
        self.assertIn('FEX QTE: OFF - 0 of 5 guest code sites patched', body)
        self.assertIn("return;", body[guard:body.index("uint64_t sites[5];", guard)])

    def test_repeat_press_call_redirect_preserves_guest_return_rip(self):
        body = body_between("static void gow3_fex_qte_callback(", "\nstatic void install_auto_qte_fex(")
        self.assertIn("if (fex_qte_sites[i].is_call)", body)
        self.assertIn("fex_qte_sites[i].address + 5", body)
        self.assertIn("gow3_fex_prepare_guest_call(regs, return_rip)", body)
        self.assertIn("regs->rip = fex_qte_sites[i].trampoline", body)
        self.assertIn("memcpy((void *)call_rsp, &next_rip, sizeof(next_rip))", HELPER)
        self.assertIn("regs->gpr[GUEST_RSP] = call_rsp", HELPER)
        self.assertIn("(unsigned char)(i == 2)", PROBE)

    def test_native_x86_gameplay_paths_untouched(self):
        self.assertIn("if (gpu_enabled) install_cheats(app0, segments, ns, size);", PROBE)
        self.assertIn("if (gpu_enabled) install_cheats_fex(app0, segments, ns, size);", PROBE)
        self.assertIn("if (gpu_enabled) install_auto_qte_fex(segments, ns, size);", PROBE)

if __name__ == "__main__":
    unittest.main()
