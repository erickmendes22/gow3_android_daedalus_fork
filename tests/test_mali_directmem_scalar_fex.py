"""Direct-memory guest log should not inherit undefined AArch64 x1 as x86 RDX.

The real allocations were 4194304 bytes before and after the guest printed
garbage. Preserving a *caller-saved* register for this one scalar import is
ABI-safe; other imports may legitimately return 128 bits in RDX:RAX.
"""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class FexDirectMemoryReturnTests(unittest.TestCase):
    def test_direct_memory_i32_return_has_targeted_rdx_preservation(self):
        source=(ROOT/"cpu/guest_cpu_fex.cpp").read_text()
        self.assertIn("direct_memory_scalar_return.load(std::memory_order_relaxed)",source)
        self.assertIn("if (fn != direct_memory_scalar_return.load",source)
        self.assertIn("s.gregs[REG_RDX] = result.x[1];",source)
        self.assertIn("s.gregs[REG_RAX] = result.x[0];",source)
        self.assertIn("guest_cpu_mark_direct_memory_scalar_return(void* fn)",source)
        self.assertIn('GOW3_DIRECTMEM_PRESERVE_RDX',source)
        self.assertIn('__attribute__((visibility("default")))',source)
        # The tagged return is scalar i32. Do NOT change the generic ABI
        # that still supplies RDX for real 128-bit guest function results.
        self.assertNotIn("s.gregs[REG_RDX] = args.x[2];",source)

    def test_runtime_tags_both_name_and_real_kernel_nid(self):
        runtime=(ROOT/"src/runtime_memory.c").read_text()
        start=runtime.index("uintptr_t runtime_memory_resolve(const char *name)")
        resolver=runtime[start: start+1100]
        self.assertIn('rTXw65xmLIA#libkernel',resolver)
        self.assertIn('sceKernelAllocateDirectMemory',resolver)
        self.assertIn("guest_cpu_mark_direct_memory_scalar_return((void *)direct_allocate)",resolver)
        self.assertIn('guest_cpu_mark_direct_memory_scalar_return(void *fn) __attribute__((weak))',runtime)
        self.assertIn("blocks[slot] = (Block){start, size, type, 1}",runtime)
        self.assertIn('size=%" PRIu64 " bytes',runtime)


if __name__=="__main__":
    unittest.main()
