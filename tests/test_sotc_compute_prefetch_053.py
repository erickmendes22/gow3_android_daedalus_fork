#!/usr/bin/env python3
"""Forest 0.1.53: prefetch worker correctness contracts and setting preservation."""
import sys
import tempfile
import shutil
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ports/sotc/android"))
from stage_sotc_compute_prefetch_053 import patch_prefetch
SRC=ROOT/"upstream-sotc/gpu"
FILES=(
    "shadps4/video_core/amdgpu/liverpool.h",
    "shadps4/video_core/amdgpu/liverpool.cpp",
    "shadps4/video_core/renderer_vulkan/vk_pipeline_cache.h",
    "shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp",
    "shadps4/video_core/renderer_vulkan/vk_rasterizer.h",
    "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp",
    "shadps4/video_core/sotc_stats.h",
)

class ForestPrefetch(unittest.TestCase):
    def test_launch_settings_and_readback_opt_in(self):
        script=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
        java=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        ui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        for key in ("SOTC_COMPUTE_PREFETCH","SOTC_VM_GAP_CACHE"):
            self.assertIn(f"export {key}=1",script)
            self.assertIn(f'env.put("{key}","1");',java)
        # The user's optional, manually enabled readback setting is unchanged.
        self.assertIn('export SOTC_RB_HOT=${SOTC_RB_HOT:-0}',script)
        self.assertIn('"1".equals(setting("sotc_pc072_fast_readbacks_050"))',java)
        self.assertIn('values["sotc_pc072_fast_readbacks_050"]',ui)

    @unittest.skipUnless((SRC/"shadps4").is_dir(),"Pinned source needed")
    def test_staged_cpu_shader_prefetch_invariants(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"gpu"
            for rel in FILES:
                (root/rel).parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(SRC/rel,root/rel)
            patch_prefetch(root)
            pc=(root/FILES[3]).read_text()
            l=(root/FILES[1]).read_text()
            rh=(root/FILES[4]).read_text()
            self.assertIn("PrefetchComputeShaders(dcb, cs, 0);",l)
            self.assertIn("PrefetchComputeShaders(acb, cs, 0);",l)
            self.assertIn("header->type3.NumWords()",l)
            self.assertIn("if (depth < 4",l)
            self.assertIn("if (!nested && rasterizer && ComputePrefetchEnabled())",l)
            self.assertIn("PrefetchCompute(const AmdGpu::ComputeProgram& cs)",pc)
            self.assertIn("WaitPrefetchedCompute(u64 hash)",pc)
            self.assertIn("std::chrono::seconds(2)",pc)
            self.assertIn("pending_programs.erase(hash)",pc)
            self.assertIn("async_done_cv.notify_all();",pc)
            self.assertIn("cs_override ? *cs_override",pc)
            self.assertIn("void PrefetchComputeShader",rh)
            with self.assertRaisesRegex(ValueError,"source drift"):
                patch_prefetch(root)

if __name__=="__main__":
    unittest.main()
