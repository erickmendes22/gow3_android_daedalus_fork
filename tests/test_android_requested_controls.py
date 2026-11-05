"""Exercise physical face-button swaps and Bionic fit/fill geometry."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class RequestedControlsTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'), 'C compiler required')
    def test_fit_and_fullscreen_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work/'geometry.c'
            source.write_text('''#include <assert.h>
#include "tools/android/bionic/present/geometry.h"
int main(void) {
 int w,h;
 gow3_display_size(2400,1080,1280,720,0,&w,&h); assert(w==1920 && h==1080);
 gow3_display_size(2400,1080,1280,720,1,&w,&h); assert(w==2400 && h==1080);
 gow3_display_size(1080,1080,1280,720,0,&w,&h); assert(w==1080 && h==607);
 gow3_display_size(1080,1080,1280,720,1,&w,&h); assert(w==1080 && h==1080);
}''')
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(ROOT),str(source),'-o',str(work/'check')],check=True)
            subprocess.run([str(work/'check')],check=True)

    @unittest.skipUnless(shutil.which('java'), 'JDK required')
    def test_physical_swap_keeps_touch_labels_and_other_buttons(self):
        production=(ROOT/'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/PadBridge.java').read_text()
        constants=lambda cls: ','.join(f'{name}={index}' for index,name in enumerate(sorted(set(re.findall(cls+r'\.([A-Z][A-Z_0-9]+)',production))),1))
        sources={
            'android/os/Looper.java':'package android.os; public class Looper { public static Looper getMainLooper(){return null;} }',
            'android/os/Handler.java':'package android.os; public class Handler { public Handler(Looper l){} public void postDelayed(Runnable r,int n){} }',
            'android/util/Log.java':'package android.util; public class Log { public static int e(String a,String b,Throwable c){return 0;} }',
            'android/view/InputDevice.java':'package android.view; public class InputDevice {public static final int SOURCE_JOYSTICK=1;}',
            'android/view/MotionEvent.java':'package android.view; public class MotionEvent {public static final int '+constants('MotionEvent')+'; public boolean isFromSource(int s){return false;} public float getAxisValue(int a){return 0;}}',
            'android/view/KeyEvent.java':'package android.view; public class KeyEvent {public static final int '+constants('KeyEvent')+'; int scan,key; public KeyEvent(int s,int k){scan=s;key=k;} public int getScanCode(){return scan;} public int getKeyCode(){return key;} public int getAction(){return ACTION_DOWN;}}',
            'ro/cobrabm/fexdroid/PadBridge.java':production,
            'ro/cobrabm/fexdroid/Harness.java':'''package ro.cobrabm.fexdroid;
import java.io.*; import android.view.KeyEvent; import java.nio.file.Files; import java.util.Set;
class Harness { public static void main(String[] args) throws Exception {
 File state=new File(args[0],"pad.state"); PadBridge pad=new PadBridge(state);
 var name=PadBridge.class.getDeclaredMethod("name",KeyEvent.class); name.setAccessible(true);
 assert name.invoke(pad,new KeyEvent(307,0)).equals("square");
 pad.setSwapFaceButtons(true);
 assert name.invoke(pad,new KeyEvent(307,0)).equals("triangle");
 assert name.invoke(pad,new KeyEvent(308,0)).equals("square");
 assert name.invoke(pad,new KeyEvent(0,KeyEvent.KEYCODE_BUTTON_X)).equals("triangle");
 assert name.invoke(pad,new KeyEvent(0,KeyEvent.KEYCODE_BUTTON_Y)).equals("square");
 assert name.invoke(pad,new KeyEvent(304,0)).equals("cross");
 assert name.invoke(pad,new KeyEvent(305,0)).equals("circle");
 pad.virtual(Set.of("square"),128,128,128,128,false,false,0,0);
 assert Files.readString(state.toPath()).startsWith("square ");
 pad.setSwapFaceButtons(false);
 assert !Files.readString(state.toPath()).contains("square ");
 assert name.invoke(pad,new KeyEvent(307,0)).equals("square");
}}'''
        }
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory); files=[]
            for name,content in sources.items():
                path=work/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content); files.append(str(path))
            subprocess.run(['java','-m','jdk.compiler/com.sun.tools.javac.Main','-d',str(work/'classes'),*files],check=True,capture_output=True)
            subprocess.run(['java','-ea','-cp',str(work/'classes'),'ro.cobrabm.fexdroid.Harness',str(work)],check=True,capture_output=True)
