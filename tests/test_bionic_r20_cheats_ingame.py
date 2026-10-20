"""Android 2.1.7 hotfix: hide GSR2 from in-game menus without deleting it;
locate FEX cheats by SpartanPort 2.6 unique signatures across moved eboots.
These host tests do NOT prove that a particular user's retail eboot contains
the signatures, or that a hook has worked in gameplay on their hardware.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/SettingsDialog.java"
GAME = ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java"
PROBE = ROOT / "src/probe.c"
HEADER = ROOT / "src/cheat_hook.h"

class FexCheatAndIngameGuiHotfix(unittest.TestCase):
    def test_hide_gsr2_in_game_not_in_runtime(self):
        code = SETTINGS.read_text()
        show = code.split("    void show() {",1)[1].split(
            "    /** Saves the changed keys",1)[0]
        self.assertNotIn("Snapdragon Game Super Resolution",show)
        self.assertNotIn('heading(box,"GSR2 rendering preset")',show)
        self.assertNotIn('changed.put("upscaler"',show)
        self.assertNotIn('changed.put("preset"',show)
        self.assertIn('changed.put("render_resolution"',show)
        self.assertIn('changed.put("fps_limit"',show)
        drawer=GAME.read_text()
        section=drawer.split("    private void refreshDrawer() {",1)[1].split(
            "    // ----",1)[0]
        self.assertNotIn('String upscaler="off"',section)
        self.assertIn('displayResolution',section)
        # The GSR2 runtime stays available for later development.
        settings=(ROOT/"gpu/shim/gow3_settings.cpp").read_text()
        self.assertIn('if (key == "upscaler")', settings)
        self.assertIn('key == "preset"', settings)

    def test_fex_installer_uses_unique_signatures_and_exact_bytes(self):
        code=PROBE.read_text()
        fex=code.split("static void install_cheats_fex(",1)[1].split(
            "static void install_auto_qte_fex(",1)[0]
        self.assertIn("gow3_signature_find(image, size, &gow3_cheat_hooks[i].site)",fex)
        self.assertIn("gow3_cheat_signature_match(hook, image + sites[i]",fex)
        self.assertIn("guest_cpu_hook(address, hook->length",fex)
        self.assertNotIn("image + hook->offset, size - hook->offset",fex)
        header=HEADER.read_text()
        self.assertIn("Gow3Signature site;",header)
        for name in ("GOW3_CHEAT_MAGIC","GOW3_CHEAT_RAGE","GOW3_CHEAT_VERY_HARD"):
            self.assertIn(name,header)

    def test_all_eight_signatures_relocate_and_ambiguous_never_install(self):
        code = r"""
#include "src/cheat_hook.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    unsigned char image[0x6000];
    for (unsigned i = 0; i < GOW3_CHEAT_HOOK_COUNT; ++i) {
        const Gow3CheatHook *hook = &gow3_cheat_hooks[i];
        int parsed[GOW3_SIGNATURE_MAX];
        unsigned n = gow3_signature_parse(hook->site.pattern,parsed);
        assert(n && hook->site.at < n);
        const unsigned start=0x200+i*0x500;
        memset(image,0xcc,sizeof(image));
        for (unsigned j=0;j<n;++j)
            image[start+j]=(unsigned char)(parsed[j]<0?0x57:parsed[j]);
        memcpy(image+start+hook->site.at,hook->original,hook->length);
        const uint64_t target=gow3_signature_find(image,sizeof(image),&hook->site);
        if (target != start+hook->site.at) {
            fprintf(stderr,"moved signature missing index=%u got=%llu expected=%u\n",
                    i,(unsigned long long)target,start+hook->site.at);
            return 1;
        }
        assert(gow3_cheat_signature_match(hook,image+target,sizeof(image)-target));
        // The locator must fail closed when two possible sites exist.
        memcpy(image+start+0x100,image+start,n);
        assert(gow3_signature_find(image,sizeof(image),&hook->site)==UINT64_MAX);
        // An original-opcode mismatch must reject the site even if the
        // signature's wildcards permitted the changed displacement.
        image[start+0x100+hook->site.at]^=0xff;
        assert(!gow3_cheat_signature_match(hook,
                  image+start+0x100+hook->site.at,sizeof(image)-start-0x100));
    }
    puts("R20: 8 relocated cheat signatures, exact bytes, ambiguous detection OK");
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"test.c"
            exe=Path(d)/"test"
            source.write_text(code)
            result=subprocess.run(["cc","-std=c11","-O2","-Wall","-Wextra","-Werror",
                    "-I",str(ROOT),str(source),"-o",str(exe)],
                    capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__ == "__main__":
    unittest.main()
