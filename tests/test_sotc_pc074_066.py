#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""PC #308 depth-only/G-buffer exact ARM64 source and toggle regression gates."""
from pathlib import Path
import ast
import random
import unittest

ROOT = Path(__file__).resolve().parents[1]

def source(path):
    return (ROOT / path).read_text()

class SotcPc074Tests(unittest.TestCase):
    def test_pc_fastpaths_are_used_instead_of_legacy_rt_or_reg_memos(self):
        s=source("ports/sotc/android/stage_renderer.py")
        self.assertIn('pc074_exact_fastpaths',s)
        self.assertIn('patch_pc074_fastpaths(out)',s)
        self.assertIn('if not pc074_exact_fastpaths:\n        patch_sotc_rt_memo(out)',s)
        self.assertIn('if not pc074_exact_fastpaths:\n        patch_sotc_reg_snapshot(out)',s)
        self.assertIn('if not pc074_exact_fastpaths:\n        patch_pm4_redundant(out)',s)
        self.assertIn('if not pc074_exact_fastpaths:\n        patch_sun_cascades(out)',s)

    def test_arm64_exact_dword_comparison_and_ordered_backop(self):
        path="ports/sotc/android/stage_sotc_pc074_arm64.py"
        s=source(path)
        ast.parse(s)
        for invariant in (
            'src[i] != shadow[i]', 'mask |= u64{1} << i',
            'op.reg_chunks.push_back(static_cast<u32>(mask >> 32))',
            'back_chunk_serial[chunk] = serial',
            'rel_render |= (rel_mask[RelRender][chunk] & mask)',
            'DepthFastBeginCheck', 'GBufferFastCheck',
            '__asm__ __volatile__("yield" ::: "memory")',
        ):
            self.assertIn(invariant,s)
        rng=random.Random(308)
        for _ in range(500):
            before=[rng.getrandbits(32) for _ in range(64)]
            after=before.copy()
            for i in range(64):
                if rng.randrange(8)==0:
                    after[i]=rng.getrandbits(32)
            exact=sum((1 << i) for i,(a,b) in enumerate(zip(before,after)) if a!=b)
            packed=[after[i] for i in range(64) if exact & (1 << i)]
            replay=before.copy()
            j=0
            for i in range(64):
                if exact & (1 << i):
                    replay[i]=packed[j]
                    j+=1
            self.assertEqual(replay,after)
            self.assertEqual(j,exact.bit_count())

    def test_sotc_only_pc_verified_toggles_and_fallback(self):
        c=source("src/runtime_memory.c")
        self.assertIn('getenv("SOTC_PORT")',c)
        self.assertIn('(UINT64_C(1) << 39)',c)
        self.assertIn('(UINT64_C(1) << 59)',c)
        self.assertIn('(UINT64_C(1) << 60)',c)
        self.assertIn('SOTC_DEPTH_FAST',c)
        self.assertIn('SOTC_GBUFFER_FAST',c)
        self.assertIn('UINT64_C(1) << 28',c)
        self.assertIn('UINT64_C(1) << 29',c)
        shell=source("ports/sotc/android/run-sotc-bionic.sh")
        self.assertIn('export SOTC_DEPTH_FAST=',shell)
        self.assertIn('export SOTC_GBUFFER_FAST=',shell)
        self.assertNotIn('SOTC_STAGING_LARGE_KEEP_MB:-auto',shell)

    def test_pc_dlss_adapter_exports_every_used_symbol(self):
        # 0.1.66 compiled, but Android dlopen rejected its undefined
        # Vulkan::Dlssg::SetHdr(bool) before any gameplay was attempted.
        adapter=source("ports/sotc/android/vk_dlssg_android.cpp")
        signatures=(
            "void SetHdr(bool)",
            "void NoteHdrCurve(float k)",
            "float HdrCurve()",
            "bool CameraLogOnly()",
            "void NoteCamera(const AmdGpu::Regs&, u32)",
            "bool SuperResolutionUpscaling()",
        )
        for signature in signatures:
            self.assertIn(signature,adapter,signature)
        self.assertIn("std::atomic<float> s_hdr_curve{1.0f}",adapter)
        self.assertIn("return s_hdr_curve.load",adapter)
        self.assertNotIn("windows.h",adapter)
        self.assertNotIn("LoadLibrary",adapter)

    def test_aot_identity_without_fex_or_tso(self):
        gradle=source("android-launcher/app/build.gradle.kts")
        self.assertIn("versionCode = 10069",gradle)
        self.assertIn('versionName = "0.1.69-aot-ux"',gradle)
        self.assertIn('applicationId = "com.sotc.android.daedalus"',gradle)
        package=source("ports/sotc/android/package_sotc_runtime.py")
        self.assertIn("version='0.1.69-aot-ux'",package)
        self.assertIn("strict_aot=os.environ.get('SOTC_REQUIRE_ON_DEVICE_AOT')=='1'",package)

if __name__ == '__main__':
    unittest.main()
