"""Exercise launcher preference -> native process environment, using the production manager."""
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest
from test_android_driver_archive import library

ROOT=Path(__file__).resolve().parents[1]


class DriverManagerTests(unittest.TestCase):
    def test_selection_survives_runtime_upgrade_and_system_clears_custom_driver(self):
        java=shutil.which('java')
        if not java:self.skipTest('JDK required')
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            driver=work/'files/gpu-drivers'/('a'*64)
            driver.mkdir(parents=True)
            (driver/'libcustom.so').write_bytes(library())
            (driver/'.driver-info.properties').write_text('name=Fixture driver\nlibrary=libcustom.so\nminApi=28\n')
            sources={
'android/content/Context.java':'''package android.content;
import java.io.*; import java.util.*;
public class Context {
 public static final int MODE_PRIVATE=0;
 final File files; public final Prefs prefs=new Prefs();
 public Context(File files) { this.files=files; }
 public File getFilesDir() { return files; }
 public String getPackageName() { return "com.gow3.android.bionic"; }
 public String getString(int id) { return "fixture error "+id; }
 public Prefs getSharedPreferences(String n,int mode) { return prefs; }
 public ContentResolver getContentResolver() { return new ContentResolver(); }
 public android.content.res.AssetManager getAssets() { return new android.content.res.AssetManager(); }
 public static class Prefs {
  final Map<String,String> values=new HashMap<>();
  public String getString(String k,String d) { return values.getOrDefault(k,d); }
  public Prefs edit() { return this; }
  public Prefs putString(String k,String v) { values.put(k,v); return this; }
  public boolean commit() { return true; }
 }
}''',
'android/content/ContentResolver.java':'''package android.content;
public class ContentResolver { public java.io.InputStream openInputStream(android.net.Uri uri) throws java.io.IOException { throw new java.io.IOException("unused"); } }''',
'android/net/Uri.java':'package android.net; public class Uri {}',
'android/os/Build.java':'package android.os; public class Build { public static final String HARDWARE="qcom", SOC_MANUFACTURER="Qualcomm"; public static class VERSION { public static final int SDK_INT=30; } }',
'android/content/res/AssetManager.java':'''package android.content.res;
public class AssetManager { public java.io.InputStream open(String path) throws java.io.IOException { throw new java.io.IOException("not used by non-Mali fixture"); } }''',
'android/util/Log.java':'''package android.util;
public class Log { public static int w(String tag,String msg,Throwable error) { return 0; } }''',
'android/opengl/EGLDisplay.java':'package android.opengl; public class EGLDisplay {}',
'android/opengl/EGLContext.java':'package android.opengl; public class EGLContext {}',
'android/opengl/EGLSurface.java':'package android.opengl; public class EGLSurface {}',
'android/opengl/EGLConfig.java':'package android.opengl; public class EGLConfig {}',
'android/opengl/GLES20.java':'package android.opengl; public class GLES20 { public static final int GL_RENDERER=0x1F01; public static String glGetString(int key) { return "Adreno"; } }',
'android/opengl/EGL14.java':'''package android.opengl;
public class EGL14 {
 public static final int EGL_DEFAULT_DISPLAY=0, EGL_RENDERABLE_TYPE=1, EGL_OPENGL_ES2_BIT=4,
  EGL_SURFACE_TYPE=2, EGL_PBUFFER_BIT=1, EGL_NONE=12344,
  EGL_CONTEXT_CLIENT_VERSION=12440, EGL_WIDTH=12375, EGL_HEIGHT=12374;
 public static final EGLDisplay EGL_NO_DISPLAY=new EGLDisplay();
 public static final EGLContext EGL_NO_CONTEXT=new EGLContext();
 public static final EGLSurface EGL_NO_SURFACE=new EGLSurface();
 public static EGLDisplay eglGetDisplay(int d) { return EGL_NO_DISPLAY; }
 public static boolean eglInitialize(EGLDisplay d,int[] major,int a,int[] minor,int b) { return false; }
 public static boolean eglChooseConfig(EGLDisplay d,int[] attrs,int offset,EGLConfig[] out,int start,int size,int[] count,int countOffset) { return false; }
 public static EGLContext eglCreateContext(EGLDisplay d,EGLConfig c,EGLContext share,int[] attrs,int offset) { return EGL_NO_CONTEXT; }
 public static EGLSurface eglCreatePbufferSurface(EGLDisplay d,EGLConfig c,int[] attrs,int offset) { return EGL_NO_SURFACE; }
 public static boolean eglMakeCurrent(EGLDisplay d,EGLSurface draw,EGLSurface read,EGLContext ctx) { return false; }
 public static boolean eglDestroySurface(EGLDisplay d,EGLSurface s) { return true; }
 public static boolean eglDestroyContext(EGLDisplay d,EGLContext ctx) { return true; }
 public static boolean eglTerminate(EGLDisplay d) { return true; }
}''',
'com/gow3/android/R.java':'package com.gow3.android; public class R { public static class string { public static final int gpu_driver_invalid=1,gpu_driver_wrong_abi=2,gpu_driver_newer_android=3; } }',
'org/json/JSONObject.java':'''package org.json; public class JSONObject {
 public JSONObject(String text) {} public int getInt(String name) { throw new UnsupportedOperationException(); }
 public String getString(String name) { throw new UnsupportedOperationException(); }
 public boolean has(String name) { return false; }
 public int optInt(String name,int fallback) { return fallback; }
 public String optString(String name,String fallback) { return fallback; }
}''',
'Harness.java':'''import java.io.*; import java.util.*;
import ro.cobrabm.fexdroid.GpuDriverManager;
class Harness {
 public static void main(String[] args) throws Exception {
  File files=new File(args[0],"files"); android.content.Context context=new android.content.Context(files);
  Map<String,String> env=new HashMap<>();
  assert GpuDriverManager.selected(context).equals("auto");
  assert GpuDriverManager.installed(context).size()==1;
  String id=GpuDriverManager.installed(context).get(0).id;
  GpuDriverManager.select(context,"custom:"+id);
  GpuDriverManager.configureEnvironment(context,env);
  assert env.get("GOW3_BIONIC_DRIVER").equals("custom");
  assert new File(env.get("GOW3_CUSTOM_VULKAN_DRIVER")).isFile();
  // Runtime updates replace gow3port; imported drivers are deliberately outside it.
  File runtime=new File(files,"gow3port"); runtime.mkdirs(); assert runtime.delete();
  GpuDriverManager.configureEnvironment(context,env);
  assert env.get("GOW3_BIONIC_DRIVER").equals("custom");
  assert GpuDriverManager.selected(context).equals("custom:"+id);
  for (String mode:new String[]{"system","gen8","adreno7xx","auto"}) {
   env.put("GOW3_VULKAN_DRIVER","old");
   GpuDriverManager.select(context,mode); GpuDriverManager.configureEnvironment(context,env);
   assert env.get("GOW3_BIONIC_DRIVER").equals(mode);
   assert !env.containsKey("GOW3_CUSTOM_VULKAN_DRIVER") && !env.containsKey("GOW3_VULKAN_DRIVER");
  }
  GpuDriverManager.select(context,"custom:"+id);
  assert GpuDriverManager.installed(context).get(0).library.delete();
  boolean failed=false;
  try { GpuDriverManager.configureEnvironment(context,env); } catch (IOException e) { failed=true; }
  assert failed; // explicit selection cannot silently use system/bundled driver
  GpuDriverManager.select(context,"system"); GpuDriverManager.configureEnvironment(context,env);
  assert env.get("GOW3_BIONIC_DRIVER").equals("system");
  assert !env.containsKey("GOW3_CUSTOM_VULKAN_DRIVER");
 }
}'''}
            paths=[]
            for name,source in sources.items():
                p=work/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(source);paths.append(str(p))
            paths += [str(ROOT/'android-launcher/app/src/main/java/ro/cobrabm/fexdroid'/name) for name in ['DriverArchive.java','GpuDriverManager.java']]
            subprocess.run([java,'-m','jdk.compiler/com.sun.tools.javac.Main','-d',str(work),*paths],check=True,text=True,capture_output=True)
            subprocess.run([java,'-ea','-cp',str(work),'Harness',str(work)],check=True,text=True,capture_output=True)
