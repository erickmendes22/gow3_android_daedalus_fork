"""The Mali read-after-read image barrier elision preserves write and layout hazards."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "gpu/shadps4/video_core/texture_cache/image.cpp").read_text()
HDR = (ROOT / "gpu/shadps4/video_core/texture_cache/image.h").read_text()
RUN = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()

class ImageBarrierTests(unittest.TestCase):
    def test_real_cplusplus_policy(self):
        compiler = shutil.which("c++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("host c++ compiler unavailable")
        source = r"""
            #include "gpu/shadps4/video_core/texture_cache/read_barrier_policy.h"
            using VideoCore::CanElideReadOnlyImageBarrier;
            static_assert(CanElideReadOnlyImageBarrier(true,true,false,false));
            static_assert(!CanElideReadOnlyImageBarrier(false,true,false,false));
            static_assert(!CanElideReadOnlyImageBarrier(true,false,false,false));
            static_assert(!CanElideReadOnlyImageBarrier(true,true,true,false));
            static_assert(!CanElideReadOnlyImageBarrier(true,true,false,true));
            static_assert(!CanElideReadOnlyImageBarrier(true,true,true,true));
            int main() { return 0; }
        """
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "read_barrier_policy")
            subprocess.run([compiler,"-std=c++20","-Wall","-Wextra","-Werror",
                            "-I",str(ROOT),"-x","c++","-","-o",out],
                           input=source,text=True,check=True)
            subprocess.run([out],check=True)

    def test_source_tracks_all_readers_and_never_elides_writers(self):
        self.assertIn("mali_read_only_elision",HDR)
        self.assertIn("GOW3_MALI_IMAGE_RAR_ELIDE",SRC)
        for marker in ["eTransferWrite","eShaderWrite","eMemoryWrite",
                       "eColorAttachmentWrite","eDepthStencilAttachmentWrite",
                       "eHostWrite","eTransformFeedbackWriteEXT"]:
            self.assertIn(marker,SRC)
        self.assertIn("state.access_mask |= dst_mask;",SRC)
        self.assertIn("state.pl_stage |= dst_stage;",SRC)
        self.assertIn("preserved_read_access |= state.access_mask;",SRC)
        self.assertIn("preserved_read_stages |= state.pl_stage;",SRC)
        self.assertIn("last_state.access_mask = dst_mask | preserved_read_access;",SRC)
        self.assertIn("last_state.pl_stage = dst_stage | preserved_read_stages;",SRC)
        self.assertIn("GOW3_MALI_IMAGE_RAR_ELIDED",SRC)
        self.assertIn("legacy_hazard_mask",SRC)
        self.assertIn("state.access_mask & legacy_hazard_mask",SRC)
        self.assertIn("last_state.access_mask & legacy_hazard_mask",SRC)

    def test_contiguous_barrier_merging_keeps_hazard_identity(self):
        self.assertIn("append_subresource_barrier(vk::ImageMemoryBarrier2{", SRC)
        self.assertIn("const bool same_dependency =", SRC)
        for guard in ("previous.image == barrier.image",
                      "previous.srcStageMask == barrier.srcStageMask",
                      "previous.srcAccessMask == barrier.srcAccessMask",
                      "previous.dstStageMask == barrier.dstStageMask",
                      "previous.dstAccessMask == barrier.dstAccessMask",
                      "previous.oldLayout == barrier.oldLayout",
                      "previous.newLayout == barrier.newLayout",
                      "previous.subresourceRange.aspectMask == barrier.subresourceRange.aspectMask",
                      "a.baseArrayLayer + a.layerCount == b.baseArrayLayer",
                      "a.baseMipLevel + a.levelCount == b.baseMipLevel"):
            self.assertIn(guard, SRC)
        self.assertIn("if (mali_read_only_elision && !barriers.empty())", SRC)

    def test_opt_out_and_vendor(self):
        self.assertIn("vendorID == 0x13B5",SRC)
        self.assertIn("GOW3_MALI_IMAGE_RAR_ELIDE=${GOW3_MALI_IMAGE_RAR_ELIDE:-1}",RUN)

if __name__ == "__main__":
    unittest.main()
