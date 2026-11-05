"""Reproduce the null-function crash with the real ImGui Vulkan backend loader."""
from paths import ROOT
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('g++'), 'g++ required')
class BionicImGuiLoader(unittest.TestCase):
    def test_ahb_without_wsi_and_missing_render_function(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'imgui-loader'
            subprocess.run([
                'g++', '-std=c++17', '-O1', '-ffunction-sections', '-fdata-sections',
                '-DIMGUI_IMPL_VULKAN_NO_PROTOTYPES', '-DVK_NO_PROTOTYPES',
                '-I'+str(ROOT/'gpu/shim'), '-I'+str(ROOT/'gpu/third_party/imgui'),
                '-I'+str(ROOT/'gpu/third_party/imgui/backends'),
                '-I'+str(ROOT/'third_party/FEX/External/Vulkan-Headers/include'),
                str(ROOT/'tests/test_bionic_imgui_loader.cpp'),
                str(ROOT/'gpu/third_party/imgui/backends/imgui_impl_vulkan.cpp'),
                '-Wl,--gc-sections', '-o', str(binary)], check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)
