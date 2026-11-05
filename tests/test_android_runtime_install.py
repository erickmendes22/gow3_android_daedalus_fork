"""Run the real runtime installer against a signed-payload fixture on a host JVM."""
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuntimeInstallTests(unittest.TestCase):
    def test_first_install_repair_and_failed_update_preserve_user_data(self):
        self.exercise_install(False)

    def test_bionic_first_install_repair_and_failed_update_preserve_user_data(self):
        self.exercise_install(True)

    def exercise_install(self, bionic):
        java = shutil.which('java') or '/usr/lib/jvm/java-17-openjdk-amd64/bin/java'
        if not Path(java).exists() or not shutil.which('tar'):
            self.skipTest('Host JVM/tar unavailable')
        modules = subprocess.run([java, '--list-modules'], capture_output=True, text=True)
        if 'jdk.compiler@' not in modules.stdout:
            self.skipTest('JVM compiler module unavailable')
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            assets = work / 'assets'
            assets.mkdir()
            fixture = work / 'fixture'
            manifest_path = ROOT / 'tools/android/runtime/runtime-manifest.json'
            manifest = json.loads(manifest_path.read_text())
            if bionic:
                manifest = {
                    'schema': 1, 'runtime_backend': 'bionic',
                    'application_id': 'com.gow3.android.bionic', 'java_package': 'ro.cobrabm.fexdroid',
                    'required_paths': [
                        {'path': 'gow3port/'+p, 'type': 'executable'} for p in [
                            'run-bionic.sh','arm64/bin/gow3-probe','arm64/bin/gow3-prepare',
                            'arm64/bin/kgsl-chip-id','arm64/bin/orbis-pkg-util','arm64/python/bin/python3.13']
                    ] + [{'path': 'gow3port/'+p, 'type': 'file'} for p in [
                        'arm64/lib/libgow3cpu.so','arm64/lib/libgow3gpu.so',
                        'arm64/lib/libgow3present.so','arm64/lib/libc++_shared.so',
                        'arm64/python/lib/libpython3.13.so','arm64/drivers/gen8/libvulkan_freedreno.so']],
                    'required_directories': ['home/gow3port'], 'loader': 'unused',
                }
            for entry in manifest['required_paths']:
                path = fixture / entry['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
                if entry['type'] == 'executable' or entry['path'] == manifest['loader']:
                    path.chmod(0o755)
            for name in manifest['required_directories']:
                (fixture / name).mkdir(parents=True, exist_ok=True)
            if not bionic:
                (fixture / 'rootfs/bin').symlink_to('usr/bin', target_is_directory=True)
            (fixture / 'home/gow3port').mkdir(parents=True, exist_ok=True)
            (fixture / 'runtime-manifest.json').write_text(json.dumps(manifest))
            (fixture / 'gow3port/gow3.default.ini').write_bytes(
                (ROOT / 'tools/android/config/gow3-default.ini').read_bytes())
            payload = assets / 'runtime.payload'
            with tarfile.open(payload, 'w:gz') as archive:
                for path in sorted(fixture.iterdir()):
                    archive.add(path, arcname=path.name)
            (assets / 'runtime.sha256').write_text(hashlib.sha256(payload.read_bytes()).hexdigest())
            sources = {
                'android/content/res/AssetManager.java': '''package android.content.res;
import java.io.*;
public class AssetManager {
 private final File root;
 public AssetManager(File root) { this.root=root; }
 public InputStream open(String name) throws Exception { return new FileInputStream(new File(root,name)); }
}''',
                'android/content/Context.java': '''package android.content;
import android.content.res.AssetManager;
public class Context {
 private final AssetManager assets;
 public Context(AssetManager assets) { this.assets=assets; }
 public AssetManager getAssets() { return assets; }
}''',
                'TestInstall.java': '''import java.io.*;
import java.nio.file.*;
import android.content.Context;
import android.content.res.AssetManager;
import ro.cobrabm.fexdroid.RuntimeInstaller;
public class TestInstall {
 public static void main(String[] args) throws Exception {
  File files=new File(args[0]); files.mkdirs();
  File assets=new File(args[1]); Context context=new Context(new AssetManager(assets));
  Path ini=files.toPath().resolve("gow3port/gow3.ini");
  Path save=files.toPath().resolve("gow3port/user/savedata/slot/save.bin");
  Files.createDirectories(save.getParent());
  Files.writeString(ini,"show_fps=1\\noverlay_corner=4\\n");
  Files.writeString(save,"keep-save");
  File extractor=new File(files,"gow3port/arm64/bin/orbis-pkg-util");
  assert !extractor.exists();
  assert RuntimeInstaller.ensure(context,files,s -> {});
  assert extractor.canExecute();
  if (Boolean.parseBoolean(args[2])) assert !new File(files,"rootfs").exists();
  assert Files.readString(ini).contains("overlay_corner=4");
  assert Files.readString(save).equals("keep-save");
  assert Files.readString(ini).contains("render_resolution=720p");
  assert Files.readString(ini).contains("deferred_readback=1");
  // Reproduce the reported partial INI even with an already-current runtime.
  Files.writeString(ini,"# custom\\nshow_fps=1\\nengine_fps=240\\ncustom_key=keep\\n");
  assert !RuntimeInstaller.ensure(context,files,s -> {});
  String repaired=Files.readString(ini);
  assert repaired.contains("render_resolution=720p");
  assert repaired.contains("engine_fps=240");
  assert !repaired.contains("engine_fps=120");
  assert repaired.contains("custom_key=keep");
  assert repaired.startsWith("# custom");
  assert !RuntimeInstaller.ensure(context,files,s -> {});
  assert Files.readString(ini).equals(repaired);
  Files.writeString(ini,repaired+"overlay_corner=4\\n");
  Files.delete(extractor.toPath()); // stale marker must not suppress repair
  assert RuntimeInstaller.ensure(context,files,s -> {});
  assert extractor.canExecute();
  assert Files.readString(save).equals("keep-save");
  Files.delete(new File(files,".runtime.sha256").toPath());
  Files.write(new File(assets,"runtime.payload").toPath(),new byte[]{1},StandardOpenOption.APPEND);
  boolean failed=false;
  try { RuntimeInstaller.ensure(context,files,s -> {}); }
  catch (IllegalStateException error) { failed=error.getMessage().contains("checksum"); }
  assert failed;
  assert extractor.canExecute();
  assert Files.readString(ini).contains("overlay_corner=4");
  assert Files.readString(save).equals("keep-save");
 }
}''',
            }
            installer = (ROOT / 'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/RuntimeInstaller.java').read_text()
            # Only replace the Android system tar location for the host fixture.
            sources['ro/cobrabm/fexdroid/RuntimeInstaller.java'] = installer.replace('"/system/bin/tar"', json.dumps(shutil.which('tar')))
            paths = []
            for name, content in sources.items():
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                paths.append(str(path))
            classes = work / 'classes'
            subprocess.run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-d', str(classes), *paths],
                           check=True, capture_output=True, text=True, timeout=30)
            result = subprocess.run([java, '-ea', '-cp', str(classes), 'TestInstall', str(work / 'files'), str(assets), str(bionic).lower()],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
