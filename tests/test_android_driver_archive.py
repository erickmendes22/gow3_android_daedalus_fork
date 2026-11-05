"""Run the production transactional ZIP/ELF importer on a host JVM."""
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def library(machine=183, needed=b'libc.so\0'):
    # Minimal ET_DYN with a load segment, dynamic string table and DT_NEEDED.
    data=bytearray(384)
    data[:64]=struct.pack('<16sHHIQQQIHHHHHH',b'\x7fELF\x02\x01\x01'+b'\0'*9,3,machine,1,0,64,0,0,64,56,2,0,0,0)
    struct.pack_into('<IIQQQQQQ',data,64,1,4,0,0,0,len(data),len(data),4096)
    struct.pack_into('<IIQQQQQQ',data,120,2,4,176,176,176,64,64,8)
    for i,pair in enumerate([(5,256),(10,len(needed)),(1,0),(0,0)]):struct.pack_into('<QQ',data,176+i*16,*pair)
    data[256:256+len(needed)]=needed
    return data


class DriverArchiveTests(unittest.TestCase):
    def test_valid_zip_rejections_and_failed_import_preserves_driver(self):
        java=shutil.which('java')
        if not java:self.skipTest('JDK required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def archive(name,entries):
                p=root/name
                with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
                    for path,data in entries:z.writestr(path,data)
                return p
            meta=json.dumps({'schemaVersion':1,'name':'Test driver','libraryName':'libvulkan.so','minApi':28})
            archive('good.zip',[('meta.json',meta),('libvulkan.so',library())])
            archive('nested.zip',[('bundle/meta.json',meta),('bundle/libvulkan.so',library())])
            archive('traversal.zip',[('../escaped',b'bad'),('meta.json',meta),('libvulkan.so',library())])
            archive('wrong.zip',[('meta.json',meta),('libvulkan.so',library(62))])
            archive('glibc.zip',[('meta.json',meta),('libvulkan.so',library(needed=b'libc.so.6\0'))])
            archive('missing.zip',[('meta.json',meta)])
            archive('ambiguous.zip',[('meta.json',meta),('other/meta.json',meta),('libvulkan.so',library())])
            archive('large.zip',[('meta.json',' '*65537),('libvulkan.so',library())])
            (root/'Harness.java').write_text('''import java.io.*;
import ro.cobrabm.fexdroid.DriverArchive;
class Harness {
 static DriverArchive.Metadata meta(File f) { return new DriverArchive.Metadata("Test driver","libvulkan.so",28); }
 static DriverArchive.Installed install(File root,String zip) throws Exception {
  try (InputStream in=new FileInputStream(new File(root.getParentFile(),zip))) {
   return DriverArchive.install(root,in,30,Harness::meta);
  }
 }
 public static void main(String[] args) throws Exception {
  File base=new File(args[0]),store=new File(base,"gpu-drivers");
  DriverArchive.Installed good=install(store,"good.zip");
  assert good.library.isFile() && good.id.matches("[0-9a-f]{64}");
  assert good.id.equals(install(store,"good.zip").id);
  assert install(store,"nested.zip").library.isFile();
  for (String bad:new String[]{"traversal.zip","wrong.zip","glibc.zip","missing.zip","ambiguous.zip","large.zip"}) {
   boolean failed=false;
   try { install(store,bad); } catch (Exception e) { failed=true; }
   assert failed:bad;
   assert DriverArchive.read(store,good.id,30).library.isFile();
  }
  assert !new File(base,"escaped").exists();
  try (InputStream in=new FileInputStream(new File(base,"good.zip"))) {
   boolean rejected=false;
   try { DriverArchive.install(store,in,30,f -> new DriverArchive.Metadata("Future","libvulkan.so",40)); }
   catch (DriverArchive.Rejected e) { rejected=e.reason==DriverArchive.Reason.NEWER_ANDROID; }
   assert rejected;
  }
  // Stream failure cannot leave a selected-looking package or destroy the old import.
  try { DriverArchive.install(store,new InputStream() { public int read() throws IOException { throw new IOException("fixture"); } },30,Harness::meta); }
  catch (IOException expected) {}
  assert DriverArchive.read(store,good.id,30).library.isFile();
  for (File f:store.listFiles()) assert !f.getName().startsWith("."):f;
  for (String id:new String[]{"../other","system",""}) {
   boolean failed=false; try { DriverArchive.read(store,id,30); } catch (IOException e) { failed=true; } assert failed;
  }
 }
}''')
            subprocess.run([java,'-m','jdk.compiler/com.sun.tools.javac.Main','-d',str(root),str(root/'Harness.java'),
                str(ROOT/'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/DriverArchive.java')],check=True,text=True,capture_output=True)
            subprocess.run([java,'-ea','-cp',str(root),'Harness',str(root)],check=True,text=True,capture_output=True)
