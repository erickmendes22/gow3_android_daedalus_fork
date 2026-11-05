"""Execute the adapted loader against ICD and Android HAL ABI fixtures, on the host."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('g++'), 'g++ is needed for executable loader tests')
class BionicDriverLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls.temp.name)
        cls.env = dict(os.environ)
        cls.env['LD_LIBRARY_PATH'] = str(cls.tmp)
        source = cls.tmp / 'check.cpp'
        source.write_text('''#include "vk_driver_loader.h"
#include <cstdint>
int main() {
 auto g = gow3_vk_get_instance_proc_addr();
 if (!g) return 11;
 auto create = g(nullptr,"vkCreateInstance");
 auto enumerate = g(nullptr,"vkEnumerateInstanceExtensionProperties");
 auto layers = g(nullptr,"vkEnumerateInstanceLayerProperties");
 if (!create || !enumerate || !layers) return 12;
 uint32_t count=9;
 auto f=reinterpret_cast<int(*)(uint32_t*,void*)>(layers);
 return f(&count,nullptr)==0 && count==0 ? 0 : 13;
}
''')
        subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I'+str(ROOT/'gpu/shim'),
                        str(source), str(ROOT/'gpu/shim/vk_driver_loader.cpp'), '-ldl', '-pthread',
                        '-o', str(cls.tmp/'check')], check=True, capture_output=True)
        cls.hal = '''#include <cstdint>
#include <cstring>
using Fn=void(*)();
struct Module;
struct Device { uint32_t tag,version; Module* module; uint64_t reserved[12]; int(*close)(Device*); };
struct Methods { int(*open)(const Module*,const char*,Device**); };
struct Module { uint32_t tag; uint16_t api,hal; const char *id,*name,*author; Methods* methods; void* dso; uint64_t reserved[25]; };
struct VkDevice { Device common; Fn ext,create; Fn(*gipa)(void*,const char*); };
void noop() {}
Fn gipa(void*,const char*) { return nullptr; } // HAL globals are intentionally not returned.
VkDevice dev{{0x48574454,0x10000,nullptr,{},nullptr},noop,noop,gipa};
int open(const Module*,const char* name,Device** out) {
 if (strcmp(name,"vk0")) return -1;
 *out=&dev.common; return 0;
}
Methods methods{open};
extern "C" { Module HMI{0x48574d54,1,0,"vulkan","mock HAL","test",&methods,nullptr,{}}; }
'''
        cls.icd = '''#include <cstdint>
#include <cstring>
void noop() {}
int layers(uint32_t* n,void*) { *n=0; return 0; }
using Fn=void(*)();
extern "C" Fn vk_icdGetInstanceProcAddr(void*,const char* name) {
 if (!strcmp(name,"vkEnumerateInstanceLayerProperties")) return reinterpret_cast<Fn>(layers);
 return noop;
}
extern "C" int vk_icdNegotiateLoaderICDInterfaceVersion(uint32_t* v) { return *v==5 ? 0 : -1; }
'''

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_library(self, code, name='driver.so', custom=True):
        source = self.tmp/'fixture.cpp'
        source.write_text(code)
        library = self.tmp/name
        subprocess.run(['g++','-std=c++17','-shared','-fPIC',str(source),'-o',str(library)],
                       check=True, capture_output=True)
        env = dict(self.env)
        if custom:
            env['GOW3_VULKAN_DRIVER'] = str(library)
        else:
            env.pop('GOW3_VULKAN_DRIVER', None)
        return subprocess.run([str(self.tmp/'check')], env=env, text=True, capture_output=True)

    def test_hal_global_entrypoint_fallback_and_empty_layers(self):
        run = self.run_library(self.hal)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('via HAL module HMI', run.stderr)

    def test_icd_negotiates_and_loads(self):
        run = self.run_library(self.icd)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('via vk_icdGetInstanceProcAddr', run.stderr)

    def test_rejected_negotiation_does_not_fallback(self):
        run = self.run_library(self.icd.replace('return *v==5 ? 0 : -1;', 'return -1;'))
        self.assertEqual(run.returncode, 11)
        self.assertIn('rejected ICD interface', run.stderr)

    def test_wrong_hal_tag_is_rejected(self):
        run = self.run_library(self.hal.replace('Module HMI{0x48574d54', 'Module HMI{0'))
        self.assertEqual(run.returncode, 11)
        self.assertIn('wrong module tag', run.stderr)

    def test_wrong_hal_device_version_is_rejected(self):
        run = self.run_library(self.hal.replace('0x48574454,0x10000', '0x48574454,0x20000'))
        self.assertEqual(run.returncode, 11)
        self.assertIn('unexpected HAL device', run.stderr)

    def test_hal_open_failure(self):
        run = self.run_library(self.hal.replace('*out=&dev.common; return 0;', '*out=nullptr; return -1;'))
        self.assertEqual(run.returncode, 11)
        self.assertIn('opening HAL device', run.stderr)

    def test_missing_vulkan_entrypoint_is_rejected(self):
        run = self.run_library('extern "C" int unrelated() { return 1; }')
        self.assertEqual(run.returncode, 11)
        self.assertIn('exports none of', run.stderr)

    def test_system_loader(self):
        code = self.icd.replace('vk_icdGetInstanceProcAddr', 'vkGetInstanceProcAddr')
        run = self.run_library(code, name='libvulkan.so.1', custom=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('system loader', run.stderr)


class BionicDriverSelection(unittest.TestCase):
    def test_auto_and_explicit_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base/'bin').mkdir()
            (base/'drivers/gen8').mkdir(parents=True)
            driver = base/'drivers/gen8/libvulkan_freedreno.so'
            driver.touch()
            runner = base/'check-driver.sh'
            runner.write_text((ROOT/'tools/android/bionic/check-driver.sh').read_text())
            chiptool = base/'bin/kgsl-chip-id'
            probe = base/'bin/gow3-vulkan-check'
            probe.write_text('#!/bin/sh\nprintf "%s" "${GOW3_VULKAN_DRIVER:-system}"\n')
            probe.chmod(0o755)
            cases = [('auto','0x44050001',str(driver)), ('auto','0x43050a01','system'),
                     ('auto','','system'), ('auto','0x44','system'),
                     ('system','0x44050001','system'), ('gen8','',str(driver))]
            for choice, chip, expected in cases:
                with self.subTest(choice=choice, chip=chip):
                    chiptool.write_text('#!/bin/sh\nprintf "%s" "'+chip+'"\n')
                    chiptool.chmod(0o755)
                    env = dict(os.environ, GOW3_BIONIC_DRIVER=choice, GOW3_VULKAN_DRIVER='stale-driver')
                    run = subprocess.run(['sh',str(runner)], env=env, text=True, capture_output=True)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertTrue(run.stdout.endswith(expected), run.stdout)
            driver.unlink()
            run = subprocess.run(['sh',str(runner)], env=dict(os.environ, GOW3_BIONIC_DRIVER='gen8'),
                                 text=True, capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('Selected driver is missing', run.stderr)

    def test_driver_pin_rejects_changed_archive(self):
        path = ROOT/'tools/android/bionic/stage_driver.py'
        spec = importlib.util.spec_from_file_location('stage_bionic_driver', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)/'driver.zip'
            archive.write_bytes(b'wrong driver')
            with self.assertRaisesRegex(ValueError, 'SHA256 differs'):
                module.stage(archive, Path(tmp)/'output')
            self.assertFalse((Path(tmp)/'output').exists())
