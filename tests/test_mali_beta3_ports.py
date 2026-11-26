from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
V=R/"gpu/shadps4/video_core"
class Beta3Ports(unittest.TestCase):
    def test_reclaim_never_touches_live_or_same_frame(self):
        s=(V/"renderer_vulkan/vk_staging_buffer_pool.cpp").read_text()
        p=s.split("void StagingBufferPool::ReclaimForAllocation(",1)[1].split("void StagingBufferPool::TickFrame",1)[0]
        for x in ("e.held || e.last_used_frame == frame","e.tick >= current || e.tick > completed",
                  "tick >= current || tick > completed","ring.blocks.size() <= 1",
                  "vmaGetHeapBudgets", "128_MB"):
            self.assertIn(x,p)
        self.assertNotIn("scheduler.Wait(",p)
        self.assertNotIn("scheduler.Finish(",p)
        self.assertNotIn("scheduler.Flush(",p)
    def test_merge_before_gpu_copy_and_cpu_publication(self):
        s=(V/"buffer_cache/buffer_cache.cpp").read_text().split("void BufferCache::DownloadMemory(",1)[1].split("namespace {",1)[0]
        self.assertLess(s.index("CoalesceAdjacentCopies(copies)"),s.index("runtime.CopyBuffer("))
        self.assertLess(s.index("scheduler.Finish();"),s.index("memory->TryWriteBacking"))
    def test_no_lowered_fidelity_or_stale_readback(self):
        r=(R/"tools/android/bionic/run-bionic.sh").read_text()
        self.assertIn("GOW3_MALI_COALESCE_DOWNLOADS:-1",r)
        self.assertIn("GOW3_MALI_STAGING_PRESSURE_RECLAIM:-1",r)
        self.assertIn("export GOW3_STALE_READBACK=0",r)
        self.assertIn("export GOW3_FRAMES_AHEAD=1",r)
if __name__=="__main__": unittest.main()
