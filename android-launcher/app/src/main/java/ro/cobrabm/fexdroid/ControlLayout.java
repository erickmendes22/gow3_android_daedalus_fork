package ro.cobrabm.fexdroid;

/** Clear the actual HUD footprint by lowering only the right shoulder row. */
final class ControlLayout {
    static float shoulderShift(float[] hud,float[][] buttons,float gap) {
        if(hud[2]<=hud[0] || hud[3]<=hud[1]) return 0;
        float shift=0;
        for(float[] b:buttons) if(hud[0]<b[2] && hud[2]>b[0] && hud[1]<b[3] && hud[3]>b[1])
            shift=Math.max(shift,hud[3]+gap-b[1]);
        return shift;
    }
    private ControlLayout() {}
}
