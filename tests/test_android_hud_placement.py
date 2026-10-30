"""Run the production HUD placement against control bounds from the reported screenshot."""
from pathlib import Path
import shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class HudPlacementTests(unittest.TestCase):
    def test_measured_hud_avoids_visible_buttons_and_preserves_free_anchors(self):
        java=shutil.which('java')
        if not java:self.skipTest('JDK required')
        code='''package ro.cobrabm.fexdroid;
class Harness {
 static boolean overlap(float x,float y,float w,float h,float[] r){return x<r[2] && x+w>r[0] && y<r[3] && y+h>r[1];}
 public static void main(String[]args){
  float[][] measured={{155,110,275,260},{402,110,525,260},{830,85,920,180},
   {975,85,1075,180},{1550,110,1670,260},{1795,100,1935,275},
   {1650,450,1780,605},{1850,500,1980,655},{1635,730,1765,880},
   {1845,720,1985,895},{960,720,1090,875},{530,375,640,480},
   {175,610,400,835},{1272,553,1482,758}};
  for(float scale:new float[]{1f,.625f,1.172f}){
   float width=2048*scale,height=922*scale,margin=8*scale;
   float[][] r=new float[measured.length][4];
   for(int i=0;i<r.length;i++)for(int j=0;j<4;j++)r[i][j]=measured[i][j]*scale;
   for(float[] size:new float[][]{{180,70},{360,116},{600,180}}){
    float w=size[0]*scale,h=size[1]*scale;
    for(int ax=0;ax<3;ax++)for(int ay=0;ay<3;ay++){
     float x=ax==0?margin:ax==1?(width-w)/2:width-w-margin;
     float y=ay==0?margin:ay==1?(height-h)/2:height-h-margin;
     float[] p=HudPlacement.place(width,height,w,h,x,y,margin,r);
     assert p[0]>=margin && p[1]>=margin && p[0]+w<=width-margin+.01f && p[1]+h<=height-margin+.01f;
     boolean originallyFree=true;
     for(float[] box:r){assert !overlap(p[0],p[1],w,h,box):"HUD covers a button";originallyFree&=!overlap(x,y,w,h,box);}
     if(originallyFree)assert p[0]==x && p[1]==y:"Unobstructed anchor moved";
    }
   }
  }
 }
}'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);h=p/'Harness.java';h.write_text(code)
            source=ROOT/'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/HudPlacement.java'
            subprocess.run([java,'-m','jdk.compiler/com.sun.tools.javac.Main','-d',directory,str(source),str(h)],check=True)
            subprocess.run([java,'-ea','-cp',directory,'ro.cobrabm.fexdroid.Harness'],check=True)
