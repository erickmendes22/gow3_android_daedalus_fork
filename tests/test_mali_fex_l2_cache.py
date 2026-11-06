"""Mali-only FEX JIT L2 cache: opt-out, no changes to guest TSO semantics."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CPU = (ROOT / "cpu/guest_cpu_fex.cpp").read_text()
LAUNCH = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()

class FexL2CacheTests(unittest.TestCase):
    def test_l2_cache_opt_in_after_fex_profile_and_before_context(self):
        config = CPU.index('FEXCore::Config::ReloadMetaLayer();')
        l2 = CPU.index('FEXCore::Config::CONFIG_DISABLEL2CACHE')
        context = CPU.index('FEXCore::Context::Context::CreateNewContext(features)')
        self.assertLess(config, l2)
        self.assertLess(l2, context)
        self.assertIn('std::getenv("GOW3_FEX_L2_CACHE")', CPU)
        self.assertIn('enable_l2 ? "0" : "1"', CPU)
        self.assertIn('if (change_l2)', CPU)
        self.assertIn('disk_cache=unchanged tso=unchanged', CPU)

    def test_mali_only_default_and_rollback(self):
        profile = LAUNCH.split('  */libvulkan_panfrost.so)', 1)[1].split(
            '# End Mali PanVK safe profile.', 1)[0]
        self.assertIn('export GOW3_FEX_L2_CACHE=${GOW3_FEX_L2_CACHE:-1}', profile)
        self.assertIn('fex_l2=$GOW3_FEX_L2_CACHE', profile)
        self.assertNotIn('export GOW3_FEX_L2_CACHE', LAUNCH.split(
            '  */libvulkan_panfrost.so)', 1)[0])

    def test_never_changes_guest_memory_ordering_or_codegen(self):
        self.assertNotIn('CONFIG_TSOENABLED', CPU)
        self.assertNotIn('CONFIG_VECTORTSOENABLED', CPU)
        self.assertNotIn('CONFIG_MEMCPYSETTSOENABLED', CPU)
        self.assertIn('CONFIG_DYNAMICL1CACHE', CPU)

if __name__ == '__main__':
    unittest.main()
