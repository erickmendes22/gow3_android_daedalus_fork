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
        # Capability queries still reach Vulkan, but reuse immutable Mali answers.\n        self.assertIn("ProbeImageFormat(instance, format_info)",image)\n        self.assertIn("instance.GetPhysicalDevice().getImageFormatProperties2(info)",image)
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

    def test_bachata_optional_descriptor_and_divisor_fallbacks(self):
        instance=src("gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp")
        header=src("gpu/shadps4/video_core/renderer_vulkan/vk_instance.h")
        pipeline=src("gpu/shadps4/video_core/renderer_vulkan/vk_graphics_pipeline.cpp")
        self.assertIn("const bool push_descriptors = add_extension(VK_KHR_PUSH_DESCRIPTOR_EXTENSION_NAME)",instance)
        self.assertIn("push_descriptor_props.maxPushDescriptors = 0;",instance)
        self.assertIn("device_chain.unlink<vk::PhysicalDeviceVertexAttributeDivisorFeatures>();",instance)
        self.assertIn("bool IsVertexAttributeDivisorSupported() const",header)
        self.assertIn("if (instance.IsVertexAttributeDivisorSupported())",pipeline)
        self.assertNotIn("ASSERT_MSG(add_extension(VK_KHR_PUSH_DESCRIPTOR_EXTENSION_NAME)",instance)

    def test_mali_original_image_layout_on_panvk(self):
        launcher=src("tools/android/bionic/run-bionic.sh")
        self.assertIn("export GOW3_PARTIAL_HEIGHT_VIEWS=0",launcher)
        self.assertIn("GOW3_MALI_CPU_PRESENT",launcher)
        self.assertIn("GOW3_PRESENT_THREAD=0",launcher)

    def test_verified_g615_auto_and_g720_isolated_driver_ab(self):
        src=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java").read_text()
        self.assertIn('return normalized.contains("g720") || normalized.contains("g615");',src)
        self.assertIn('nextPanvkVerifiedAutoDevice(Context context)',src)
        self.assertIn('migratedMaliSelection(old,true,false)',src)
        self.assertIn('MALI_DEFAULT_MIGRATION_KEY',src)
        self.assertIn('normalized.contains("g720")',src)
        self.assertIn('"com.gow3.android.bionic.malitest".equals(pkg)',src)
        self.assertIn('("auto".equals(selection) && nextPanvkVerifiedAutoDevice(context))',src)
        self.assertIn('drv = bundledPanvk(context, false);',src)
        self.assertIn('if (!"auto".equals(selection) || !wantNext) throw new IOException("Selected PanVK driver unavailable",nextFailed);',src)

if __name__=="__main__":
    unittest.main()

