#!/usr/bin/env python3
"""No-FEX SotC AOT fiber ABI source-port regression (synthetic, no game files)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "ports/sotc/android/aot/port_guest_context.py"
spec = importlib.util.spec_from_file_location("sotc_context", P)
sotc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sotc)

SOURCE = r'''#include "guest_cpu.h"
struct Gran {
    const uint8_t* flags = nullptr;    // bbr_func_granular[]
};
enum class MissKind { Call, Jump, Unwind, Patched, Outside };
void Slow() {
    if (GranularEntry(s, target, t)) return;
}
void bbr_unwound() {
        const bool ran = GranularEntry(s, s->rip, t);
}
void guest_cpu_call() {
        else if (GranularEntry(&s, rip, t)) {}
}
void LoadAotLibrary() {
    if (abi_flags && (*abi_flags & 1))
        std::fprintf(stderr, "AOT: %s has resume entries (bbr_abi_flags bit 0); this runtime does not use them\n", path);
    if (abi_flags && (*abi_flags & 16)) {   // granular entries: bbr_func_granular[] says which functions of bbr_funcs[] have them
        G.funcs = static_cast<const GranRec*>(dlsym(so, "bbr_funcs"));
        const auto* nf = static_cast<const uint64_t*>(dlsym(so, "bbr_func_count"));
        G.flags = static_cast<const uint8_t*>(dlsym(so, "bbr_func_granular"));
        G.nfuncs = nf ? *nf : 0;
        if (!G.funcs || !G.flags || !G.nfuncs) { G.flags = nullptr; std::fprintf(stderr, "AOT: %s: granular entries declared but their tables are missing\n", path); }
    }
}
thread_local Thread* self;
void CallHostFn(GuestState* s, void* fn) {
    bbcpu_host_call(fn, &a, &r);
    s->gregs[RAX] = r.x[0];
}
void HostCall(GuestState* s, void* fn) {
    CallHostFn(s, fn);
    s->gregs[RSP] = sp + 8;
    s->rip = ret;
}
extern "C" {
void guest_cpu_init() {}
}
'''

class SotcAotFiberTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.upstream = self.root / "upstream"
        self.cpu = self.upstream / "cpu"
        self.cpu.mkdir(parents=True)
        self.header = self.upstream / "src/guest_cpu.h"
        self.header.parent.mkdir()
        self.header.write_text("#pragma GCC visibility push(default)\n#pragma GCC visibility pop\n")
        for n in sotc.REQUIRED:
            (self.cpu / n).write_text(SOURCE if n == "guest_cpu_aot.cpp" else "// test\n")

    def test_generates_sotc_context_and_preserves_host_state(self):
        out = self.root / "out"
        result = sotc.generate(self.upstream, out)
        aot = (out / "guest_cpu_aot.cpp").read_text()
        header = (out / "guest_cpu.h").read_text()
        self.assertEqual(result["tso"], False)
        self.assertEqual(result["fex"], False)
        self.assertIn("AOT: native ABI v2 resume-entry dispatcher enabled",aot)
        self.assertIn("const bool ran = ResumeEntry(s, s->rip, t) || GranularEntry(s, s->rip, t)",aot)
        self.assertIn("else if (ResumeEntry(&s, rip, t) || GranularEntry(&s, rip, t))",aot)
        self.assertIn("s->_pad1 = 1;",aot)
        self.assertNotIn("this runtime does not use them",aot)
        self.assertTrue(result["aot_resume_entries"])
        self.assertIn("guest_context_get(SotcGuestContext* out)", aot)
        self.assertIn("guest_context_set(const SotcGuestContext* in)", aot)
        self.assertIn("sotc_host_replaced = true", aot)
        self.assertIn("if (sotc_host_replaced) return", aot)
        self.assertIn("if (!was_replaced)", aot)
        self.assertIn("out->gpr[RSP] += 8", aot)
        self.assertIn("out->rip = sotc_host_return", aot)
        self.assertIn("sotc_host_state = saved_host_state", aot)
        self.assertIn("SotcGuestContext;", header)
        self.assertIn("guest_context_get", header)
        self.assertNotIn("FEXCore", aot)
        self.assertNotIn("--tso", aot)
        self.assertTrue((out / "guest_state.h").is_file())

    def test_rejects_changed_upstream_host_call_contract(self):
        original = (self.cpu / "guest_cpu_aot.cpp").read_text()
        (self.cpu / "guest_cpu_aot.cpp").write_text(
            original.replace("    CallHostFn(s, fn);\n", "    CallHostFn(s, bogus);\n"))
        with self.assertRaisesRegex(ValueError, "nested SotC host call context"):
            sotc.generate(self.upstream, self.root / "bad")

    def test_does_not_write_into_original_upstream(self):
        before = (self.cpu / "guest_cpu_aot.cpp").read_bytes()
        sotc.generate(self.upstream, self.root / "out")
        self.assertEqual(before, (self.cpu / "guest_cpu_aot.cpp").read_bytes())
        self.assertEqual(self.header.read_text(),
                         "#pragma GCC visibility push(default)\n#pragma GCC visibility pop\n")

if __name__ == "__main__":
    unittest.main()
