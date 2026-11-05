"""Execute GameActivity's startup methods with deterministic Android lifecycle queues."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def method(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class RuntimeStartupTests(unittest.TestCase):
    def test_clean_install_recreation_and_install_failure(self):
        java = shutil.which('java')
        if not java:
            self.skipTest('JDK required')
        source = (ROOT/'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java').read_text()
        # These are the production startup methods, not a second implementation of their logic.
        production = '\n'.join(method(source, signature) for signature in [
            'private boolean bionicRuntime()', 'private void startRuntime(SurfaceHolder holder)'])
        harness = '''import java.io.File;
import java.util.ArrayDeque;
class Queue {
 final ArrayDeque<Runnable> tasks=new ArrayDeque<>();
 void post(Runnable r) { tasks.add(r); }
 void execute(Runnable r) { post(r); }
 void drain() { while (!tasks.isEmpty()) tasks.remove().run(); }
}
class SurfaceHolder {
 boolean valid=true;
 SurfaceHolder getSurface() { return this; }
 boolean isValid() { return valid; }
 SurfaceHolder getHolder() { return this; }
}
class Text { void setText(String text) {} }
class UiText { static String get(GameActivity activity,String value) { return value; } }
class RuntimeInstaller {
 static boolean fail;
 static int calls;
 static boolean ensure(GameActivity a,File f,java.util.function.Consumer<String> status) throws Exception {
  calls++; if (fail) throw new Exception("fixture install failed");
  a.installed=true; return true;
 }
}
class GameActivity {
 boolean destroyed,startingX,runtimeReady,installed;
 int shmid=-1,bionicStarts,xStarts,attachments,errors;
 final String FILES="unused-fixture-path";
 String packageName="com.gow3.android.bionic";
 Queue main=new Queue(),worker=new Queue();
 SurfaceHolder surface=new SurfaceHolder(); Text status=new Text();
 String getPackageName() { return packageName; }
 void startBionic(SurfaceHolder h) { assert installed; bionicStarts++; }
 void startX(SurfaceHolder h) { assert installed; xStarts++; }
 void attach(SurfaceHolder h) { assert installed; attachments++; }
 void error(String message) { errors++; }
 void drain() { worker.drain(); main.drain(); worker.drain(); }
''' + production + '''
 public static void main(String[] args) {
  GameActivity a=new GameActivity();
  assert a.bionicRuntime(); // no runtime files exist yet
  a.startRuntime(a.surface); a.startRuntime(a.surface);
  assert a.bionicStarts==0 && a.xStarts==0 && !a.installed;
  a.drain();
  assert a.bionicStarts==1 && a.xStarts==0 && RuntimeInstaller.calls==1;
  a.startRuntime(a.surface); // recreating the display must reattach the Bionic bridge
  assert a.bionicStarts==2 && RuntimeInstaller.calls==1;
  GameActivity linux=new GameActivity(); linux.packageName="com.gow3.android";
  linux.startRuntime(linux.surface); linux.drain();
  assert linux.xStarts==1 && linux.bionicStarts==0;
  linux.shmid=42; linux.startRuntime(linux.surface); assert linux.attachments==1;
  GameActivity rotated=new GameActivity(); rotated.startRuntime(rotated.surface);
  rotated.surface.valid=false; rotated.drain(); assert rotated.bionicStarts==0;
  rotated.surface=new SurfaceHolder(); rotated.startRuntime(rotated.surface);
  assert rotated.bionicStarts==1;
  GameActivity gone=new GameActivity(); gone.startRuntime(gone.surface);
  gone.destroyed=true; gone.drain(); assert gone.bionicStarts==0;
  GameActivity failed=new GameActivity(); RuntimeInstaller.fail=true;
  failed.startRuntime(failed.surface); failed.drain();
  assert failed.errors==1 && !failed.startingX && failed.bionicStarts==0;
  RuntimeInstaller.fail=false; failed.startRuntime(failed.surface); failed.drain();
  assert failed.bionicStarts==1;
 }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            path = work/'GameActivity.java'
            path.write_text(harness)
            log = work/'android/util/Log.java'
            log.parent.mkdir(parents=True)
            log.write_text('package android.util; public class Log { public static int i(String tag,String text) { return 0; } }')
            subprocess.run([java, '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-d', str(work), str(path), str(log)],
                           check=True, capture_output=True, text=True, timeout=30)
            subprocess.run([java, '-ea', '-cp', str(work), 'GameActivity'],
                           check=True, capture_output=True, text=True, timeout=30)
