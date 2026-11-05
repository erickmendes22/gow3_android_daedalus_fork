package ro.cobrabm.fexdroid;

/** Shared continuous stick vector for the game and its movable swipe indicator. */
final class DodgeMotion {
    static float[] vector(float dx,float dy,float range) {
        return new float[]{Math.max(-1,Math.min(1,dx/range)),Math.max(-1,Math.min(1,dy/range))};
    }
    static float[] indicator(float x,float y,float radiusX,float radiusY) {
        float length=(float)Math.max(1,Math.hypot(x,y));
        return new float[]{x/length*radiusX,y/length*radiusY};
    }
    private DodgeMotion() {}
}
