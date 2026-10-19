"""Regression checks for Bionic R1 save / Bloodframe / management actions.

Keep GSR2 identical to parent branch; intentionally no GSR2 settings edits.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def source(path): return (ROOT/path).read_text(encoding="utf-8")

class BionicR1RepairTests(unittest.TestCase):
    def test_save_import_is_clickable(self):
        card=source("android-launcher/app/src/main/java/com/gow3/android/feature/about/SaveCard.kt")
        self.assertIn('stringResource(R.string.save_import), true,',card)

    def test_settings_reuses_working_save_and_log_managers(self):
        ui=source("android-launcher/app/src/main/java/com/gow3/android/feature/settings/GeneralSettingsScreen.kt")
        nav=source("android-launcher/app/src/main/java/com/gow3/android/ui/LauncherScreen.kt")
        for expr in ('saves.launchExport', 'saves.launchImport', 'logs.launchExport',
                     'SaveCard(', 'LogCard('):
            self.assertIn(expr,ui)
        self.assertIn('GeneralSettingsScreen(saves, logs)',nav)

    def test_generated_image_returns_with_legal_vulkan_layout(self):
        presenter=source("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
        at=presenter.index('const vk::ImageMemoryBarrier output_release')
        self.assertIn('oldLayout = vk::ImageLayout::eTransferSrcOptimal',presenter[at:at+800])
        self.assertIn('newLayout = vk::ImageLayout::eGeneral',presenter[at:at+800])

    def test_frame_fence_reset_happens_when_real_frame_submission_is_ready(self):
        presenter=source("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
        st=presenter.index('bool Presenter::PresentWithLsfg')
        body=presenter[st:]
        self.assertTrue(body.index('const auto reset_result') > body.index('if (!swapchain.AcquireNextImage())'))
        self.assertIn('present_scheduler.Wait(present_scheduler.CurrentTick() - 1)',body)

    def test_save_thumbnail_is_real_png_not_fake_badge(self):
        save=source("src/runtime_savedata.c")
        overlay=source("gpu/shim/gow3_overlay.cpp")
        self.assertIn('PNG\\r\\n\\x1a\\n',save)
        self.assertIn('genuine per-slot icon',save)
        self.assertIn('No save preview',overlay)
        self.assertNotIn('"SAVE DATA"',overlay)

if __name__=="__main__":
    unittest.main()
