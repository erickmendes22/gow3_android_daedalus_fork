import hashlib
import importlib.util
import json
import pathlib
import struct
import tempfile
import unittest
import zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("stage",ROOT/"tools/android/bionic/stage_mali_performance_drivers.py")
stage=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

class MaliPerformanceBundle(unittest.TestCase):
    def make(self, temp, bad=False):
        p=pathlib.Path(temp)/"driver.zip"
        header=bytearray(64)
        header[:6]=b"\x7fELF\x02\x01"
        struct.pack_into("<HH",header,16,3,62 if bad else 183)
        with zipfile.ZipFile(p,"w") as z:
            z.writestr("meta.json",json.dumps({"libraryName":"libvulkan_panfrost.so","minApi":35}))
            z.writestr("libvulkan_panfrost.so",header)
        return p,hashlib.sha256(p.read_bytes()).hexdigest()
    def test_pinned_package_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            p,h=self.make(temp)
            stage.validate(p,h)
            with self.assertRaises(ValueError):
                stage.validate(p,"0"*64)
    def test_wrong_abi(self):
        with tempfile.TemporaryDirectory() as temp:
            p,h=self.make(temp,True)
            with self.assertRaises(ValueError):
                stage.validate(p,h)
    def test_launcher_matches_pins_and_safe_opt_in(self):
        j=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java").read_text()
        for d in stage.DRIVERS:
            for key in ("id","file","sha"):
                self.assertIn(d[key],j)
        self.assertIn('final boolean wantNext = "panvk-next".equals(selection);',j)
        self.assertIn('environment.put("PANVK_DEAD_DRAW","0")',j)
        self.assertIn('environment.put("PANVK_LOW_QUALITY","0")',j)
        self.assertIn('environment.put("GOW3_MALI_PREPARE_CACHED_PIPELINES","1")',j)
    def test_prepass_is_bounded_and_nonblocking(self):
        f=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp").read_text()
        s=f.split("void PipelineCache::PrepareCachedMaliPipelines",1)[1].split("bool PipelineCache::StartBackgroundWarmUp",1)[0]
        self.assertIn("StartSafeMaliWarmUp(true)",s)
        self.assertIn("std::chrono::seconds(12)",s)
        self.assertIn("std::chrono::steady_clock::now() < deadline",s)
        self.assertIn("std::this_thread::sleep_for(std::chrono::milliseconds(4))",s)
        self.assertIn("PumpWarmUp()",s)
        self.assertNotIn("pool->Wait",s)
        self.assertNotIn("StopWarmUp()",s)

if __name__=="__main__": unittest.main()
