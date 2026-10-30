#!/usr/bin/env python3
"""Compile-test the injected SotC Android ImGui Vulkan loader before building ARM64."""
import argparse
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
args = parser.parse_args()
src = args.source.read_text()

def section_between(start, end):
    a = src.index(start)
    b = src.index(end, a)
    return src[a:b]

try:
    guard = section_between('static bool SotcUnusedDesktopVkFunction(const char* name)',
                            '#else\\nstatic bool SotcUnusedDesktopVkFunction')
    macro = section_between('#define IMGUI_VULKAN_FUNC_LOAD(func)',
                            '    IMGUI_VULKAN_FUNC_MAP(IMGUI_VULKAN_FUNC_LOAD)')
except ValueError as ex:
    sys.exit(f'Injected SotC ImGui Vulkan loader is missing or incompatible: {ex}')
if 'std::fprintf' in macro or '::fprintf(' not in macro:
    sys.exit('SotC ImGui error logging must use ::fprintf with <stdio.h>')
if 'SotcUnusedDesktopVkFunction(#func)' not in macro:
    sys.exit('Required Vulkan functions are not being validated')
source = '''#include <stdio.h>
#include <cstring>
using PFN_vkVoidFunction = void (*)();
static PFN_vkVoidFunction loader_func(const char*, void*) { return nullptr; }
static PFN_vkVoidFunction vkGetPhysicalDeviceProperties = nullptr;
static PFN_vkVoidFunction vkCreateSwapchainKHR = nullptr;
''' + guard + '\\n' + macro + '''
bool sotc_loader_compile_test() {
    void* user_data = nullptr;
    IMGUI_VULKAN_FUNC_LOAD(vkGetPhysicalDeviceProperties)
    IMGUI_VULKAN_FUNC_LOAD(vkCreateSwapchainKHR)
    return true;
}
'''
cmd = ['clang++', '-std=c++23', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
       '-D__ANDROID__', '-x', 'c++', '-fsyntax-only', '-']
result = subprocess.run(cmd, input=source, text=True, capture_output=True)
if result.returncode != 0:
    sys.exit('SotC ImGui Vulkan loader preflight failed:\\n' + result.stderr)
print('SotC Android ImGui Vulkan injected guard and macro: clang++ C++23 syntax OK')
