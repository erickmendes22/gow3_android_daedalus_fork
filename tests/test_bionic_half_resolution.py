"""Make sure low-resolution patches update the game's half-resolution bloom targets.

Upstream FelipePrado0/gow3_pc#613, as ported by zFitness/gow3_android.
These patch writes are essential: a 960x540 postprocessing table with a
854x480 scene creates blown-out highlights at 480p/900p.
"""
import pathlib
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
XML = ROOT / "patches" / "God_of_War_III_Remastered.xml"
HALF_WIDTH = "00 00 00 00 0a e0 f2 00 c0 03 00 00 1c 02 00 00 01 00 00 00"
HALF_HEIGHT = "0a e0 f2 00 c0 03 00 00 1c 02 00 00 01 00 00 00 00 00 00 00"

class HalfResolutionPostprocessingTests(unittest.TestCase):
    def test_480p_720p_and_900p_follow_half_output(self):
        root = ET.parse(XML).getroot()
        expected = {"480p": (427, 240), "720p": (640, 360), "900p": (800, 450)}
        for resolution, dims in expected.items():
            with self.subTest(resolution=resolution):
                matches = [x for x in root.findall(".//Metadata")
                           if x.get("Name") == "Resolution Patch - " + resolution
                           and x.get("AppVer") == "01.02"]
                self.assertEqual(len(matches), 1)
                lines = {x.get("Pattern"): x for x in matches[0].findall("./PatchList/Line")
                         if x.get("Pattern") in (HALF_WIDTH, HALF_HEIGHT)}
                self.assertEqual(len(lines), 2)
                self.assertEqual(lines[HALF_WIDTH].get("Address"), "0x007f2a3c")
                self.assertEqual(lines[HALF_HEIGHT].get("Address"), "0x007f2a40")
                decoded = lambda p: int.from_bytes(bytes.fromhex(lines[p].get("Value")), "little")
                self.assertEqual((decoded(HALF_WIDTH), decoded(HALF_HEIGHT)), dims)

if __name__ == "__main__":
    unittest.main()
