#!/usr/bin/env python3
"""SotC-only TAA history: avoid previous-frame ghosts without muting scene lighting."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"ports/sotc/android/run-sotc-bionic.sh"
GAME=ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java"
UI=ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt"

class NativeTaaHistoryTest(unittest.TestCase):
    def test_environment_off_by_default_for_sotc_only(self):
        s=RUN.read_text()
        self.assertIn('export SOTC_TAA_OFF=${SOTC_TAA_OFF:-1}',s)
        self.assertIn('SotC native TAA: temporal history disabled',s)
        self.assertIn('SotC native TAA: temporal history enabled',s)
        self.assertIn('export BB_READBACKS=2',s)
        self.assertIn('export SOTC_RB_ASYNC=0',s)
        self.assertIn('gpu-user-srt-phi5-turnip-nomultipos',s)

    def test_launch_environment_respects_user_choice(self):
        code=GAME.read_text()
        self.assertIn('env.put("SOTC_TAA_OFF",',code)
        self.assertIn('"1".equals(setting("sotc_taa_history")) ? "0" : "1"',code)
        self.assertIn('env.put("SOTC_ADRENO_WAVE32",',code)
        self.assertIn('env.put("SOTC_CVARS",cvars);',code)

    def test_reversible_ui_pt_en_with_restart(self):
        code=UI.read_text()
        self.assertIn('Histórico temporal TAA (ghosts)',code)
        self.assertIn('TAA temporal history (ghosts)',code)
        self.assertIn('(values["sotc_taa_history"]?:"0")=="1"',code)
        self.assertIn('save("sotc_taa_history",if(it)"1" else "0")',code)
        self.assertIn('Reinicie o jogo após mudar.',code)

if __name__ == "__main__":
    unittest.main()
