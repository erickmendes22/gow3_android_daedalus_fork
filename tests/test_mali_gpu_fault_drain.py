from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]/"gpu/shadps4/video_core"
F=(R/"buffer_cache/fault_manager.cpp").read_text()
B=(R/"buffer_cache/buffer_cache.cpp").read_text()
V=(R/"renderer_vulkan/vk_rasterizer.cpp").read_text()
S=(R/"host_shaders/fault_buffer_process.comp").read_text()
class FaultDrain(unittest.TestCase):
 def test_mali_no_recursive_submission_from_retirement(self):
    self.assertIn("if (!mali_safe_fault_drain) {\n        scheduler.DeferOperation",F)
    d=F.split("void FaultManager::DrainCompletedFaults()",1)[1].split("void FaultManager::ResolveFaultArea",1)[0]
    self.assertIn("scheduler.GetWorkSemaphore()->IsFree(tick)",d)
    self.assertNotIn("scheduler.Wait(",d)
    self.assertIn("ResolveFaultArea(next_completed_area)",d)
    self.assertIn("buffer_cache.DrainCompletedFaults();",V)
 def test_bounds_and_cache_coherency(self):
    self.assertIn("FaultResultCount(reported, MaxPageFaults)",F)
    self.assertIn("download_buffer.Invalidate(offset, PageFaultAreaSize)",F)
    self.assertIn("download_buffer.Flush(offset, PageFaultAreaSize)",F)
    self.assertIn("atomicOr(fault_buffer[id], word)",S)
    self.assertIn("runtime.FillBuffer(fault_buffer, 0, fault_buffer->SizeBytes(), 0u)",B)
 def test_dma_publishes_memory(self):
    self.assertIn("buffer_cache.SynchronizeDmaBuffers();",V)
    d=V.split("if (uses_dma) {",1)[1].split("return true;",1)[0]
    self.assertIn("runtime.FlushBarriers(true);",d)
if __name__=="__main__": unittest.main()
