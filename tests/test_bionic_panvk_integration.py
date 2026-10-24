"""Regression checks for opt-in, pre-GSR Bionic Mali driver integration."""
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
JAVA=ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid"
UPSCALER=ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp"
DRIVER_HASH="68d4eccc1442cb0bef08228c90127388e68bf6087898abc492c717b9a06ca61f"


class MaliPanvkTests(unittest.TestCase):
    def test_branch_does_not_include_gsr2(self):
        text=UPSCALER.read_text()
        for term in ("GSR2", "Gsr2", "gsr2"):
            self.assertNotIn(term,text)

    def test_auto_select_is_strictly_mali_android15(self):
        text=(JAVA/"GpuDriverManager.java").read_text()
        self.assertIn('new File("/dev/mali0").exists()',text)
        self.assertIn('new File("/dev/kgsl-3d0").exists()',text)
        self.assertIn('Build.VERSION.SDK_INT<35',text)
        self.assertIn('"auto".equals(selection) && maliCandidate()',text)
        self.assertIn('environment.put("GOW3_BIONIC_DRIVER","custom")',text)
        self.assertIn('environment.put("GOW3_BIONIC_DRIVER","system")',text)
        self.assertIn('environment.put("GOW3_CUSTOM_VULKAN_DRIVER",drv.library.getAbsolutePath())',text)
        self.assertIn('DriverArchive.validateLibrary(drv.library)',text)
        self.assertIn('PANVK_SHA256="'+DRIVER_HASH+'"',text)

    def test_automated_packaging_uses_pinned_archive(self):
        script=(ROOT/"tools/android/bionic/fetch_panvk.sh").read_text()
        build=(ROOT/"tools/android/bionic/build_apk.sh").read_text()
        self.assertIn(DRIVER_HASH,script)
        self.assertIn('sha256sum -c --status',script)
        self.assertIn('out/android-release/assets/drivers',script)
        self.assertIn('PanVK-android-v3.2-universal-2a9358a.zip',script)
        self.assertIn('tools/android/bionic/fetch_panvk.sh',build)

    def test_user_driver_setting_is_not_overwritten(self):
        text=(JAVA/"GpuDriverManager.java").read_text()
        self.assertIn('selection.startsWith("custom:")',text)
        self.assertIn('else if ("panvk".equals(value))',text)
        ui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/feature/home/GpuDriverCard.kt").read_text()
        self.assertIn('GpuDriverManager.automaticDescription(context)',ui)
        self.assertIn('GpuDriverManager.maliCandidate()',ui)
        self.assertIn('PanVK 3.2 (Mali, experimental)',ui)

    def test_existing_adreno_selection_is_preserved(self):
        script=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()
        self.assertIn('turnip=gen8',script)
        self.assertIn('turnip=adreno7xx',script)
        self.assertIn('GOW3_VULKAN_DRIVER',script)
        java=(JAVA/"GpuDriverManager.java").read_text()
        self.assertIn('"auto","gen8","adreno7xx","system"',java)

if __name__=="__main__":
    unittest.main()
