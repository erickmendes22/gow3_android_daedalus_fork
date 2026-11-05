"""Exercise continuous dodge vectors and shoulder clearance for the approved layout."""
from pathlib import Path
import shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class MobileLayoutTests(unittest.TestCase):
    def test_real_motion_and_hud_clearance(self):
        java=shutil.which('java')
        if not java:self.skipTest('JDK required')
        code='''package ro.cobrabm.fexdroid;
class Harness {
 static boolean overlap(float[] a,float[] b){return a[0]<b[2] && a[2]>b[0] && a[1]<b[3] && a[3]>b[1];}
 public static void main(String[]args){
  for(float scale:new float[]{.625f,1f,1.172f}) {
   float[][] buttons={{1550*scale,174*scale,1670*scale,310*scale},{1795*scale,164*scale,1935*scale,325*scale}};
   for(float height:new float[]{116,180,240}) {
    float[] hud={1680*scale,8*scale,2028*scale,(8+height)*scale};
    float[] original=hud.clone();
    float shift=ControlLayout.shoulderShift(hud,buttons,12*scale);
    for(int i=0;i<4;i++)assert hud[i]==original[i]:"Selected HUD anchor moved";
    for(float[] b:buttons) assert !overlap(hud,new float[]{b[0],b[1]+shift,b[2],b[3]+shift}):"Shoulders still cover HUD";
    if(height==116) assert shift==0:"Approved lower row moved unnecessarily";
   }
   assert ControlLayout.shoulderShift(new float[4],buttons,12)==0:"Hidden HUD still reserves space";
  }
  float[] idle=DodgeMotion.vector(0,0,56);assert idle[0]==0 && idle[1]==0:"Tap triggers dodge";
  float[] half=DodgeMotion.vector(28,0,56);assert half[0]==.5f && half[1]==0:"Motion is not continuous";
  for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++) {
   float[] move=DodgeMotion.vector(x*112,y*112,56);
   assert move[0]==x && move[1]==y:"Wrong game direction or out-of-range axis";
   float[] p=DodgeMotion.indicator(move[0],move[1],32,19);
   assert p[0]*p[0]/(32*32)+p[1]*p[1]/(19*19)<=1.0001:"Indicator escaped swipe rim";
   assert Math.signum(p[0])==x && Math.signum(p[1])==y:"Indicator disagrees with game";
  }
  float[] reset=DodgeMotion.indicator(0,0,32,19);assert reset[0]==0 && reset[1]==0:"Release did not recenter";
 }
}'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);h=p/'Harness.java';h.write_text(code)
            source=ROOT/'android-launcher/app/src/main/java/ro/cobrabm/fexdroid'
            subprocess.run([java,'-m','jdk.compiler/com.sun.tools.javac.Main','-d',directory,str(source/'ControlLayout.java'),str(source/'DodgeMotion.java'),str(h)],check=True)
            subprocess.run([java,'-ea','-cp',directory,'ro.cobrabm.fexdroid.Harness'],check=True)
