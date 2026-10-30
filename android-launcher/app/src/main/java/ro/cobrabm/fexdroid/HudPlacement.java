package ro.cobrabm.fexdroid;

/** Places the measured HUD near its chosen anchor without covering touch controls. */
final class HudPlacement {
    static float[] place(float width,float height,float w,float h,float preferredX,float preferredY,
                         float margin,float[][] obstacles) {
        float maxX=Math.max(margin,width-margin-w),maxY=Math.max(margin,height-margin-h);
        float[] xs=new float[3+2*obstacles.length],ys=new float[xs.length];
        xs[0]=preferredX;xs[1]=margin;xs[2]=maxX;
        ys[0]=preferredY;ys[1]=margin;ys[2]=maxY;
        for(int i=0;i<obstacles.length;i++) {
            float[] r=obstacles[i];
            xs[3+2*i]=r[0]-w-margin;xs[4+2*i]=r[2]+margin;
            ys[3+2*i]=r[1]-h-margin;ys[4+2*i]=r[3]+margin;
        }
        float best=Float.POSITIVE_INFINITY,bx=preferredX,by=preferredY;
        for(float x:xs) for(float y:ys) {
            if(x<margin || x>maxX || y<margin || y>maxY) continue;
            boolean blocked=false;
            for(float[] r:obstacles) if(x<r[2] && x+w>r[0] && y<r[3] && y+h>r[1]) {blocked=true;break;}
            if(blocked)continue;
            float distance=(x-preferredX)*(x-preferredX)+(y-preferredY)*(y-preferredY);
            if(distance<best) {best=distance;bx=x;by=y;}
        }
        return new float[]{bx,by};
    }
    private HudPlacement() {}
}
