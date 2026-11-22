#!/usr/bin/env python3
"""SotC SSE4.2 PCMPISTRX reference-vs-hardware tests, all control combinations.

On x86_64 with SSE4.2, the host CPU supplies Intel's actual flag/result semantics.
The portable implementation intentionally mirrors the new LLVM lowering design;
it is NOT a substitute for compiling/testing the LLVM backend itself.
"""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import platform
import random
import shutil
import subprocess
import tempfile
import unittest

CPP=r"""
#include <nmmintrin.h>
#include <cstdint>
struct Result { uint32_t mask, flags; };
template <int C> static inline Result eval(const uint8_t* a,const uint8_t* b){
    __m128i x=_mm_loadu_si128((const __m128i*)a);
    __m128i y=_mm_loadu_si128((const __m128i*)b);
    uint32_t result=(uint32_t)_mm_cvtsi128_si32(_mm_cmpistrm(x,y,C & 0x3f));
    uint32_t flags=(_mm_cmpistrs(x,y,C)<<31) | (_mm_cmpistrz(x,y,C)<<30)
                   | (_mm_cmpistrc(x,y,C)<<29) | (_mm_cmpistro(x,y,C)<<28);
    return {result,flags};
}
extern "C" Result oracle(const uint8_t* a,const uint8_t* b,int control){
    switch(control){
"""

def reference(lhs:bytes,rhs:bytes,control:int)->tuple[int,int]:
    width=2 if control&1 else 1
    n=16//width
    signed=bool(control&2)
    def elements(data):
        values=[int.from_bytes(data[i*width:(i+1)*width],"little",signed=signed)
                for i in range(n)]
        length=next((i for i,v in enumerate(values) if v==0),n)
        return values,length
    a,alen=elements(lhs);b,blen=elements(rhs)
    mode=(control>>2)&3
    result=0
    for j in range(n):
        if mode==0:
            active=j<blen and any(b[j]==a[i] for i in range(alen))
        elif mode==1:
            active=j<blen and any(a[i]<=b[j]<=a[i+1] for i in range(0,alen-1,2))
        elif mode==2:
            active=(j>=alen and j>=blen) or (
                j<alen and j<blen and a[j]==b[j])
        else:
            active=alen==0 or (
                j<blen and (blen==n or j+alen<=blen)
                and all(a[i]==b[i+j] for i in range(min(alen,blen-j))))
        if active:result|=1<<j
    polarity=(control>>4)&3
    if polarity==1:result^=(1<<n)-1
    if polarity==3:result^=(1<<blen)-1
    flags=((alen<n)<<31)|((blen<n)<<30)|((result!=0)<<29)|((bool(result&1))<<28)
    return result,flags

class NativeSse42Oracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if platform.machine().lower() not in ("x86_64","amd64"):
            raise unittest.SkipTest("SSE4.2 oracle requires an x86-64 host")
        if not shutil.which("g++"):
            raise unittest.SkipTest("Need g++ to compile host SIMD reference")
        try:
            flags=Path("/proc/cpuinfo").read_text()
        except OSError:
            flags=""
        if "sse4_2" not in flags:
            raise unittest.SkipTest("Host CPU does not advertise SSE4.2")
        cls.tmp=tempfile.TemporaryDirectory()
        src=Path(cls.tmp.name)/"oracle.cpp"
        so=Path(cls.tmp.name)/"oracle.so"
        body=CPP+"\n".join(
            f"    case {i}: return eval<{i}>(a,b);" for i in range(128))
        body+="\n    default: return {0,0};\n    }\n}\n"
        src.write_text(body)
        subprocess.run(["g++","-std=c++17","-O2","-fPIC","-shared","-msse4.2",
                        str(src),"-o",str(so)],check=True)
        class Result(ctypes.Structure):
            _fields_=[("mask",ctypes.c_uint32),("flags",ctypes.c_uint32)]
        cls.lib=ctypes.CDLL(str(so))
        cls.lib.oracle.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
        cls.lib.oracle.restype=Result

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"tmp"):cls.tmp.cleanup()

    def test_23680_sse42_reference_vectors(self):
        rng=random.Random(33)
        cases=[]
        for _ in range(100):
            cases.append((
                bytes(rng.randrange(256) if rng.random()>.22 else 0 for _ in range(16)),
                bytes(rng.randrange(256) if rng.random()>.22 else 0 for _ in range(16))))
        for _ in range(35):
            cases.append((bytes(rng.randrange(65,91) for _ in range(16)),
                          bytes(rng.randrange(65,91) for _ in range(16))))
        for _ in range(50):
            cases.append((bytes(rng.randrange(256) for _ in range(16)),
                          bytes(rng.randrange(256) for _ in range(16))))
        self.assertEqual(len(cases),185)
        for control in range(128):
            for lhs,rhs in cases:
                p=ctypes.create_string_buffer(lhs)
                q=ctypes.create_string_buffer(rhs)
                actual=self.lib.oracle(ctypes.addressof(p),ctypes.addressof(q),control)
                expected=reference(lhs,rhs,control)
                self.assertEqual((actual.mask,actual.flags),expected,
                                 f"control {control:#x}; lhs={lhs.hex()} rhs={rhs.hex()}")

if __name__=="__main__":
    unittest.main()
