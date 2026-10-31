#!/usr/bin/env python3
"""Turnip geometry integrity: disable IR3 multi-position on SotC Adreno."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "ports/sotc/android/run-sotc-bionic.sh"

def turnip_flag(source: str, driver: str, initial: str = "") -> str:
    start = source.index('case "$driver" in\n  gen8|adreno7xx)')
    end = source.index("\nexport GOW3_ANDROID_INPUT=1", start)
    shell = 'driver="$1"; TU_DEBUG="$2";\n' + source[start:end] + '\nprintf "EFFECTIVE=%s\n" "$TU_DEBUG"'
    p = subprocess.run(["sh", "-c", shell, "sotc-test", driver, initial],
                       capture_output=True, text=True, check=True)
    return p.stdout.split("EFFECTIVE=", 1)[1].strip()

class TurnipGeometry(unittest.TestCase):
    def test_mesa_driver_gets_real_ir3_geometry_fix(self):
        s = RUNNER.read_text()
        self.assertIn('nomultipos"; export TU_DEBUG', s)
        self.assertIn('gen8|adreno7xx)', s)
        self.assertIn('SotC Turnip vertex integrity: nomultipos requested', s)
        self.assertLess(s.index("nomultipos"), s.index('exec "$@"'))
        self.assertEqual(turnip_flag(s, "gen8"), "nomultipos")
        self.assertEqual(turnip_flag(s, "adreno7xx"), "nomultipos")

    def test_preserves_existing_flags_without_duplicates(self):
        s = RUNNER.read_text()
        self.assertEqual(turnip_flag(s, "gen8", "sysmem"), "sysmem,nomultipos")
        self.assertEqual(turnip_flag(s, "gen8", "nomultipos"), "nomultipos")
        self.assertEqual(turnip_flag(s, "gen8", "sysmem,nomultipos"), "sysmem,nomultipos")
        self.assertEqual(turnip_flag(s, "gen8", "nolrz,sysmem"), "nolrz,sysmem,nomultipos")

    def test_does_not_force_turnip_debug_on_system_or_custom(self):
        s = RUNNER.read_text()
        self.assertEqual(turnip_flag(s, "system"), "")
        self.assertEqual(turnip_flag(s, "custom", "noubwc"), "noubwc")

    def test_shader_cache_and_proven_workarounds_stay_intact(self):
        s = RUNNER.read_text()
        self.assertIn("gpu-user-srt-phi6-gs-position-turnip-nomultipos-$sotc_gpu_profile", s)
        self.assertIn("sotc_gpu_profile=wave32", s)
        self.assertIn("sotc_gpu_profile=wave64", s)
        self.assertIn("export SOTC_ANDROID_FRAGMENT_TSHARP=1", s)
        self.assertIn("export SOTC_RB_ASYNC=0", s)
        self.assertIn("export BB_READBACKS=2", s)
        self.assertIn("export SOTC_TAA_OFF=", s)
        self.assertNotIn("export SOTC_ADRENO_WAVE32=0", s)

if __name__ == "__main__":
    unittest.main()
