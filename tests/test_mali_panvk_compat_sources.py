"""Source guards for PanVK compressed image handling and driver A/B.
They do not substitute for native compile or real Mali gameplay validation.
"""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def src(path):
    return (ROOT/path).read_text()

class MaliPanvkCompatSourceTests(unittest.TestCase):
    def test_mali_bcn_only_preserves_compressed_mip_layout(self):
        image=src("gpu/shadps4/video_core/texture_cache/image.cpp")
        self.assertIn("info.props.is_block",image)
        self.assertIn("getImageFormatProperties2(format_info)",image)
        self.assertIn("vk::ImageCreateFlagBits::eExtendedUsage",image)
        self.assertIn("getProperties().vendorID == 0x13B5",image)
        self.assertIn("flags = format_info.flags;",image)
        self.assertIn("PanVK BCn image compatibility",image)

    def test_updated_panvk_is_optional_and_verified(self):
        java=src("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java")
        script=src("tools/android/bionic/fetch_panvk.sh")
        self.assertIn("PANVK_NEXT_ZIP",java)
        self.assertIn('"panvk-next".equals(selection)',java)
        self.assertIn("bundledPanvk(context,",java)
        self.assertIn("0c61ef0cdd5c9314715c4a0cc34a5929dbd727ce7a30545b947577e83600b900",script)
        self.assertIn("zenithblue-oss/panvk-kbase-android",script)
        self.assertIn("sha256sum -c --status",script)
        self.assertIn("PanVK-android-v3.2-universal-2a9358a.zip",script)
        self.assertNotIn('environment.put("GOW3_BIONIC_DRIVER","gen8")',java)

if __name__=="__main__":
    unittest.main()
