#!/usr/bin/env python3
"""Pinned-source regression for SotC-specific renderer effects."""
from pathlib import Path
import importlib.util
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
UPSTREAM=ROOT/"upstream-sotc/gpu/shadps4/video_core/renderer_vulkan"
STAGE=ROOT/"ports/sotc/android/stage_sotc_rt_memo.py"
spec=importlib.util.spec_from_file_location("sotc_rt_memo",STAGE)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class SotcRtMemo(unittest.TestCase):
    def test_off_by_default_and_reversible(self):
        run=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
        java=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        ui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        stage=(ROOT/"ports/sotc/android/stage_renderer.py").read_text()
        self.assertIn("export SOTC_RT_MEMO=$"+"{SOTC_RT_MEMO:-1}",run)
        self.assertIn('env.put("SOTC_RT_MEMO",',java)
        self.assertIn('save("sotc_rt_memo",if(it)"1" else "0")',ui)
        self.assertIn("patch_sotc_rt_memo(out)",stage)

    @unittest.skipUnless(UPSTREAM.is_dir(),"Pinned renderer checkout required")
    def test_staged_cpp_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"gpu/shadps4/video_core/renderer_vulkan"
            p.mkdir(parents=True)
            for file in ("vk_rasterizer.cpp","vk_rasterizer.h"):
                shutil.copy2(UPSTREAM/file,p/file)
            mod.patch_sotc_rt_memo(p.parents[2])
            cpp=(p/"vk_rasterizer.cpp").read_text()
            hdr=(p/"vk_rasterizer.h").read_text()
            self.assertEqual(cpp.count("RenderState Rasterizer::BeginRendering("),1)
            self.assertEqual(cpp.count("RenderState Rasterizer::BeginRenderingFull("),1)
            for marker in ("scheduler.IsRendering()", "scheduler.GetRenderState() == rt_memo.state",
                           "RtMemoAttachmentsSafe(sig)", "texture_cache.IsMetaCleared(sig.cmask[i]",
                           "texture_cache.IsMetaCleared(sig.htile", "ImageFlagBits::Dirty",
                           "image.binding.needs_rebind", "image.usage.vo_surface", "Dlssg::UiTarget(",
                           "texture_cache.TestAndTouchMeta(htile_address, slice)",
                           "texture_cache.TestAndTouchMeta(col_buf.CmaskAddress(), slice)",
                           "RefreshImageLayouts();", "scheduler.BeginRendering(state);",
                           "bool Rasterizer::BindResources"):
                self.assertIn(marker,cpp)
            self.assertIn("struct RtMemoSignature",hdr)
            with self.assertRaisesRegex(ValueError,"source drift"):
                mod.patch_sotc_rt_memo(p.parents[2])

if __name__=="__main__": unittest.main()
