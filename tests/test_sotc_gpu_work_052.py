#!/usr/bin/env python3
"""GPU optimization 0.1.52: verify staging and launcher integration."""
import sys, shutil, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ports/sotc/android"))
from stage_sotc_pc_streaming_051 import patch_pc_streaming
from stage_sotc_gpu_work_052 import patch_gpu_work
SRC=ROOT/"upstream-sotc/gpu"
FILES=("shadps4/video_core/buffer_cache/buffer_cache.cpp",
       "shadps4/video_core/buffer_cache/buffer_cache.h",
       "shadps4/video_core/renderer_vulkan/vk_staging_buffer_pool.cpp",
       "shadps4/video_core/renderer_vulkan/vk_shader_hle.cpp")
class GpuWorkBackportTest(unittest.TestCase):
    def test_defaults(self):
        sh=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
        java=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        for name,value in (("SOTC_FILL_HLE_GPU","1"),("SOTC_TEX_ASYNC_KB","512")):
            self.assertIn(f"export {name}={value}",sh)
            self.assertIn(f'env.put("{name}","{value}");',java)
        self.assertIn("export SOTC_RB_HOT=${SOTC_RB_HOT:-0}",sh)
        self.assertIn("version='0.1.53-boot-test'",(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text())
    @unittest.skipUnless((SRC/"shadps4").is_dir(),"Pinned PC source needed")
    def test_real_cpp(self):
        with tempfile.TemporaryDirectory() as td:
            gpu=Path(td)/"gpu"
            for rel in FILES:
                (gpu/rel).parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(SRC/rel,gpu/rel)
            patch_pc_streaming(gpu)
            patch_gpu_work(gpu)
            bc=(gpu/FILES[0]).read_text()
            h=(gpu/FILES[1]).read_text()
            hle=(gpu/FILES[3]).read_text()
            for needle in ("BbCopy::Async([mem = memory, address = device_addr + offset",
                           "staging.buffer->is_coherent","JoinAsyncUploads();",
                           "BbCopy::WaitAsync();","async_uploads.store(true, std::memory_order_release)",
                           "runtime.FillBuffer(arena, dst, size, value);",
                           "runtime.CopyBuffer(arena, arena, std::span{&copy, 1});"):
                self.assertIn(needle,bc)
            self.assertIn("TryFillThroughFromCpu",h)
            self.assertIn("rasterizer.GetTextureCache().InvalidateMemory",hle)
            self.assertIn('std::getenv("SOTC_FILL_HLE_GPU")',hle)
            self.assertIn("rasterizer.InvalidateMemory(address, count * 4);",hle)
            with self.assertRaisesRegex(ValueError,"source drift"):
                patch_gpu_work(gpu)
if __name__=="__main__": unittest.main()
