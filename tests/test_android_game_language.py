"""Exercise Android menu translation and the console language passed to the game."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GameLanguageTests(unittest.TestCase):
    def test_english_and_portuguese_menu_and_game_language(self):
        java = shutil.which('java') or '/usr/lib/jvm/java-17-openjdk-amd64/bin/java'
        if not Path(java).exists():
            self.skipTest('Host JVM unavailable')
        modules = subprocess.run([java, '--list-modules'], capture_output=True, text=True)
        if 'jdk.compiler@' not in modules.stdout:
            self.skipTest('JVM compiler module unavailable')
        sources = {
            'android/content/Context.java': '''package android.content;
public class Context {
 public static final int MODE_PRIVATE=0;
 private final String language;
 public Context(String language) { this.language=language; }
 public SharedPreferences getSharedPreferences(String name,int mode) { return new SharedPreferences(language); }
}''',
            'android/content/SharedPreferences.java': '''package android.content;
public class SharedPreferences {
 private final String language;
 public SharedPreferences(String language) { this.language=language; }
 public String getString(String key,String fallback) { return language==null ? fallback : language; }
}''',
            'ro/cobrabm/fexdroid/LanguageTest.java': '''package ro.cobrabm.fexdroid;
import android.content.Context;
public class LanguageTest {
 public static void main(String[] args) {
  Context en=new Context(null), pt=new Context("pt");
  assert UiText.gameLanguage(en).equals("1");
  assert UiText.gameLanguage(pt).equals("7");
  assert UiText.get(en,"Graphics settings").equals("Graphics settings");
  assert UiText.get(pt,"Graphics settings").equals("Configurações gráficas");
  assert UiText.get(pt,"GRAPHICS").equals("GRÁFICOS");
  assert UiText.get(pt,"Resume game").equals("Continuar jogo");
  assert UiText.get(pt,"Apply & restart").equals("Aplicar e reiniciar");
  assert UiText.get(pt,"No upscaling · 120 FPS limit").equals("Sem ampliação · 120 FPS de limite");
  assert UiText.get(pt,"Sharpness: 50%").equals("Nitidez: 50%");
  assert UiText.get(pt,"720p").equals("720p");
 }
}''',
        }
        sources['com/gow3/android/data/GameSfo.java'] = """package com.gow3.android.data;
public class GameSfo { public static String portugueseLanguage(String game,String update) { return "7"; } }
"""
        sources['ro/cobrabm/fexdroid/UiText.java'] = (ROOT / 'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/UiText.java').read_text()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            paths = []
            for name, content in sources.items():
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                paths.append(str(path))
            subprocess.run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-d', str(work / 'classes'), *paths],
                           check=True, capture_output=True, text=True, timeout=30)
            result = subprocess.run([java, '-ea', '-cp', str(work / 'classes'), 'ro.cobrabm.fexdroid.LanguageTest'],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
