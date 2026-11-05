"""Fast Android resources checks that run before the native build."""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_DIR = ROOT / "android-launcher/app/src/main/res"


class AndroidStringResourcesTests(unittest.TestCase):
    def test_resource_files_are_well_formed_xml(self):
        for path in RESOURCE_DIR.glob("values*/strings.xml"):
            with self.subTest(path=str(path.relative_to(ROOT))):
                ET.parse(path)

    def test_no_unescaped_android_apostrophes(self):
        # Android AAPT2 requires escaping apostrophes inside unquoted strings.
        for path in RESOURCE_DIR.glob("values*/strings.xml"):
            root = ET.parse(path).getroot()
            for item in root.findall("string"):
                value = "".join(item.itertext())
                with self.subTest(path=str(path.relative_to(ROOT)),
                                  name=item.attrib.get("name", "")):
                    self.assertIsNone(
                        re.search(r"(?<!\\)'", value),
                        "unescaped apostrophe; use the Android backslash escape",
                    )

    def test_launch_parameter_string_identifiers_exist(self):
        values = ET.parse(RESOURCE_DIR / "values/strings.xml").getroot()
        declared = {item.get("name") for item in values if item.get("name")}
        kotlin = (ROOT / "android-launcher/app/src/main/java/"
                  "com/gow3/android/data/LaunchParams.kt").read_text()
        used = set(re.findall(r"\bR\.string\.(\w+)", kotlin))
        self.assertFalse(used - declared, f"missing string resources: {used - declared}")


if __name__ == "__main__":
    unittest.main()
