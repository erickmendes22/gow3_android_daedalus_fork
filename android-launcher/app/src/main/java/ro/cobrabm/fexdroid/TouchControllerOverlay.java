package ro.cobrabm.fexdroid;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Canvas;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.RectF;
import java.io.InputStream;
import android.graphics.Paint;
import android.graphics.PointF;
import android.graphics.Typeface;
import android.util.SparseArray;
import android.view.MotionEvent;
import android.view.View;
import java.io.File;
import android.os.SystemClock;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

/** Translucent PlayStation-style controls with a persistent, draggable layout. */
final class TouchControllerOverlay extends View {
    private static final String[] NAMES={
        "l2","l1","touchpad","options","r1","r2",
        "up","left","right","down","triangle","circle","cross","square",
        "leftstick","rage","weapons","rightstick"
    };
    // GoW III mobile layout based on the inFAMOUS Android action-pad design.
    // Guard the first 125 virtual pixels for landscape status bars/cutouts.
    // D-pad switches weapons/magic; right stick handles evasion; L3+R3 stays
    // visible for Rage. Legacy generic layouts are kept under their old keys.
    // Approved XML/preview coordinates, 1280x576. Positions span the immersive
    // window; each individual control retains a uniform scale and stays round.
    private static final float[][] DEFAULT={
        {288,106},{134,106},{548,83},{640,83},{1008,106},{1164,106},
        {364,211},{308,267},{420,267},{364,323},
        {1198,350},{1057,492},{1198,492},{1071,316},
        {179,449},{640,488},{364,267},{861,408}
    };
    private final PadBridge pad;
    private final File saveDialogFlag;
    private boolean saveDialogMode;
    private long lastSaveDialogCheck;
    private boolean dialogControlAllowed(String name) {
        return name!=null && (name.equals("dpad") || name.equals("up") ||
            name.equals("left") || name.equals("right") || name.equals("down") ||
            name.equals("cross") || name.equals("circle"));
    }
    private boolean saveDialogActive() {
        if (editing) return false;
        long now=SystemClock.uptimeMillis();
        if (now-lastSaveDialogCheck > 150) {
            lastSaveDialogCheck=now;
            boolean next=saveDialogFlag.isFile();
            if (next!=saveDialogMode) {
                saveDialogMode=next;
                release(); // no sticky held buttons when the modal appears
            }
        }
        return saveDialogMode;
    }

    private final SharedPreferences preferences;
    private final Map<String,Float> sizes=new LinkedHashMap<>();
    private PointF dodgeOrigin;
    private boolean weaponsOpen;
    private Runnable geometryListener;
    void onGeometryChanged(Runnable listener) { geometryListener=listener; }
    private void geometryChanged() { if(geometryListener!=null) geometryListener.run(); }
    private final Map<String,Bitmap> actionIcons=new LinkedHashMap<>();
    private float pinchStartDistance,pinchStartSize;
    private String key(String axis,String name) { return "gow3_mobile_v218_"+axis+"_"+name; }
    private float size(String name) {
        Float value=sizes.get(name);
        return value==null ? 1f : value;
    }
    private boolean hidden(String name) { return false; }
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Map<String,PointF> centers=new LinkedHashMap<>();
    private final SparseArray<String> controls=new SparseArray<>();
    private final SparseArray<PointF> positions=new SparseArray<>();
    private final Set<String> pressed=new LinkedHashSet<>();
    private boolean mouseDown,editing;
    private final boolean mouseEnabled;
    private int editPointer=-1;
    private String dragged;
    private Runnable onEditDone;

    TouchControllerOverlay(Context context,PadBridge pad,boolean mouseEnabled) {
        super(context); this.pad=pad; this.mouseEnabled=mouseEnabled;
        saveDialogFlag=new File(context.getFilesDir(),"gow3port/save-dialog.active");
        preferences=context.getSharedPreferences("gow3",Context.MODE_PRIVATE);
        for (int i=0;i<NAMES.length;i++) {
            String name=NAMES[i];
            centers.put(name,new PointF(preferences.getFloat(key("x",name),DEFAULT[i][0]),
                                        preferences.getFloat(key("y",name),DEFAULT[i][1])));
            sizes.put(name,Math.max(.6f,Math.min(1.6f,
                preferences.getFloat(key("size",name),1f))));
        }
        for (String name:new String[]{"l1","l2","r1","r2","square","triangle","circle","cross","rage"}) {
            try (InputStream in=context.getAssets().open("gow3-controls/"+name+".png")) {
                Bitmap icon=BitmapFactory.decodeStream(in);
                if (icon==null) throw new java.io.IOException("Invalid action icon: "+name);
                actionIcons.put(name,icon);
            } catch (java.io.IOException ex) { android.util.Log.e("GoW3","Cannot load approved control icon",ex); }
        }
        setContentDescription(UiText.get(context,"On-screen controller"));
    }
    private PointF layoutCenter(String name) {
        PointF p=centers.get(name);
        return new PointF(p.x*getWidth()/(1280f*scale()),p.y*getHeight()/(576f*scale()));
    }
    private PointF center(String name) {
        if (!editing && "rightstick".equals(name) && dodgeOrigin!=null) return dodgeOrigin;
        return layoutCenter(name); // left joystick is fixed, never follows touch-down
    }
    private float scale() { return Math.max(1e-3f,Math.min(getWidth()/1280f,getHeight()/576f)); }
    private float offsetX() { return 0f; }
    private float offsetY() { return 0f; }
    private float layoutX(MotionEvent e,int index) { return e.getX(index)/scale(); }
    private float layoutY(MotionEvent e,int index) { return e.getY(index)/scale(); }
    private void moveControl(String name,float x,float y) {
        float margin=48f*size(name);
        x=Math.max(margin,Math.min(getWidth()/scale()-margin,x));
        y=Math.max(margin,Math.min(getHeight()/scale()-margin-18,y));
        centers.get(name).set(x*scale()*1280f/getWidth(),y*scale()*576f/getHeight());
        geometryChanged();
    }
    private static float distance(float x,float y,PointF p) { return (float)Math.hypot(x-p.x,y-p.y); }
    private static boolean stick(String name) { return name.equals("leftstick") || name.equals("rightstick"); }
    private static boolean rectangle(String name) {
        return name.equals("touchpad") || name.equals("options");
    }
    private PointF dpadCenter() {
        PointF u=center("up"),l=center("left"),r=center("right"),d=center("down");
        return new PointF((u.x+l.x+r.x+d.x)/4f,(u.y+l.y+r.y+d.y)/4f);
    }
    private String hit(float x,float y) {
        final boolean save=saveDialogActive();
        PointF dpad=dpadCenter();
        if (!editing && (weaponsOpen || save) && distance(x,y,dpad)<112 && distance(center("up").x,center("up").y,dpad)<115 &&
            distance(center("left").x,center("left").y,dpad)<115 &&
            distance(center("right").x,center("right").y,dpad)<115 &&
            distance(center("down").x,center("down").y,dpad)<115) return "dpad";
        String winner=null; float best=Float.MAX_VALUE;
        for (String name:NAMES) {
            if (save && !dialogControlAllowed(name)) continue;
            if (!editing && !save && !weaponsOpen &&
                (name.equals("up") || name.equals("left") || name.equals("right") || name.equals("down"))) continue;
            PointF p=layoutCenter(name);
            float dx=Math.abs(x-p.x),dy=Math.abs(y-p.y);
            float scale=size(name);
            boolean inside=distance(x,y,p)<(stick(name) ? 72 : 44)*scale;
            if (inside && distance(x,y,p)<best) { best=distance(x,y,p); winner=name; }
        }
        if (winner!=null || editing || save) return winner;
        return null; // only the visible fixed joystick and dodge panel own analog input
    }
    private static int axis(float v) { return Math.max(0,Math.min(255,Math.round((v+1f)*127.5f))); }

    private void publish() {
        pressed.clear();
        int lx=128,ly=128,rx=128,ry=128,l2=0,r2=0;
        boolean left=false,right=false,mouse=false;
        for (int i=0;i<controls.size();i++) {
            String control=controls.valueAt(i);
            PointF p=positions.get(controls.keyAt(i));
            if (p==null) continue;
            if (control.equals("dpad")) {
                PointF c=dpadCenter();
                if (p.x<c.x-22) pressed.add("left");
                if (p.x>c.x+22) pressed.add("right");
                if (p.y<c.y-22) pressed.add("up");
                if (p.y>c.y+22) pressed.add("down");
            } else if (control.equals("leftstick")) {
                left=true; PointF c=center(control);
                lx=axis(Math.max(-1f,Math.min(1f,(p.x-c.x)/(56f*size(control)))));
                ly=axis(Math.max(-1f,Math.min(1f,(p.y-c.y)/(56f*size(control)))));
            } else if (control.equals("rightstick")) {
                right=true; PointF c=center(control);
                rx=axis(Math.max(-1f,Math.min(1f,(p.x-c.x)/(56f*size(control)))));
                ry=axis(Math.max(-1f,Math.min(1f,(p.y-c.y)/(56f*size(control)))));
            } else if (control.equals("l2")) { l2=255; pressed.add(control); }
            else if (control.equals("r2")) { r2=255; pressed.add(control); }
            else if (control.equals("touchpad")) pressed.add("touchpad_right"); /* 右侧点击:打开游戏暂停菜单,进而可进存档列表 */
            else if (control.equals("mouse")) {
                if (!mouse) XInput.moveTo(Math.max(0,Math.min(1279,Math.round(p.x))),
                                          Math.max(0,Math.min(719,Math.round(p.y))));
                mouse=true;
            } else if (control.equals("rage")) {
                pressed.add("l3"); pressed.add("r3");
            } else if (!control.equals("weapons")) pressed.add(control);
        }
        if (mouse!=mouseDown) { XInput.button(1,mouse); mouseDown=mouse; }
        pad.virtual(pressed,lx,ly,rx,ry,left,right,l2,r2);
        invalidate();
    }
    void release() {
        controls.clear(); positions.clear(); dodgeOrigin=null; publish();
    }
    void edit(Runnable done) { release(); editing=true; onEditDone=done; invalidate(); }
    private void finishEdit() {
        editPointer=-1; dragged=null; editing=false; invalidate();
        if (onEditDone!=null) onEditDone.run();
        onEditDone=null;
    }
    void resetLayout() {
        SharedPreferences.Editor editor=preferences.edit();
        for (int i=0;i<NAMES.length;i++) {
            String name=NAMES[i]; centers.get(name).set(DEFAULT[i][0],DEFAULT[i][1]);
            sizes.put(name,1f);
            editor.remove(key("x",name)).remove(key("y",name)).remove(key("size",name));
        }
        editor.apply(); release(); invalidate(); geometryChanged();
    }

    @Override protected void onSizeChanged(int w,int h,int oldw,int oldh) {
        super.onSizeChanged(w,h,oldw,oldh);
        release(); editPointer=-1; dragged=null;
    }
    @Override public boolean onTouchEvent(MotionEvent e) {
        int action=e.getActionMasked(),at=e.getActionIndex(),id=e.getPointerId(at);
        if (editing) {
            if (action==MotionEvent.ACTION_CANCEL) { editPointer=-1; dragged=null; return true; }
            if (action==MotionEvent.ACTION_DOWN) {
                float x=layoutX(e,at),y=layoutY(e,at);
                if (Math.abs(x-getWidth()/scale()/2)<92 && y>6 && y<64) { finishEdit(); return true; }
                dragged=hit(x,y); editPointer=dragged==null ? -1 : id;
                pinchStartDistance=0f;
            } else if (action==MotionEvent.ACTION_POINTER_DOWN && dragged!=null && e.getPointerCount()>=2) {
                float dx=e.getX(0)-e.getX(1),dy=e.getY(0)-e.getY(1);
                pinchStartDistance=(float)Math.hypot(dx,dy);
                pinchStartSize=size(dragged);
            } else if (action==MotionEvent.ACTION_MOVE && editPointer>=0 && dragged!=null) {
                if (e.getPointerCount()>=2 && pinchStartDistance>16f) {
                    float dx=e.getX(0)-e.getX(1),dy=e.getY(0)-e.getY(1);
                    sizes.put(dragged,Math.max(.6f,Math.min(1.6f,
                        pinchStartSize*(float)Math.hypot(dx,dy)/pinchStartDistance))); geometryChanged();
                } else {
                    int index=e.findPointerIndex(editPointer);
                    if (index>=0) moveControl(dragged,layoutX(e,index),layoutY(e,index));
                }
                invalidate();
            } else if (action==MotionEvent.ACTION_POINTER_UP) {
                pinchStartDistance=0f;
                if (dragged!=null)
                    preferences.edit().putFloat(key("size",dragged),size(dragged)).apply();
            } else if (action==MotionEvent.ACTION_UP && id==editPointer && dragged!=null) {
                PointF p=centers.get(dragged);
                preferences.edit().putFloat(key("x",dragged),p.x)
                    .putFloat(key("y",dragged),p.y).putFloat(key("size",dragged),size(dragged)).apply();
                editPointer=-1; dragged=null;
            }
            return true;
        }
        if (action==MotionEvent.ACTION_CANCEL) { release(); return true; }
        if (action==MotionEvent.ACTION_DOWN || action==MotionEvent.ACTION_POINTER_DOWN) {
            float x=layoutX(e,at),y=layoutY(e,at);
            String name=hit(x,y);
            if (name==null && !mouseEnabled) { weaponsOpen=false; invalidate(); geometryChanged(); return true; }
            if (name!=null && stick(name))
                for (int i=0;i<controls.size();i++) if (name.equals(controls.valueAt(i))) return true;
            controls.put(id,name==null ? "mouse" : name);
            positions.put(id,new PointF(x,y));
            if ("weapons".equals(name)) { weaponsOpen=!weaponsOpen; geometryChanged(); }
            if ("rightstick".equals(name)) dodgeOrigin=new PointF(x,y);
        } else if (action==MotionEvent.ACTION_UP || action==MotionEvent.ACTION_POINTER_UP) {
            String released=controls.get(id);
            controls.remove(id); positions.remove(id);
            if ("dpad".equals(released)) { weaponsOpen=false; geometryChanged(); }

            if ("rightstick".equals(released)) dodgeOrigin=null;
        }
        if (action==MotionEvent.ACTION_MOVE) {
            for (int i=0;i<e.getPointerCount();i++) {
                PointF p=positions.get(e.getPointerId(i));
                if (p!=null) p.set(layoutX(e,i),layoutY(e,i));
            }
        }
        publish(); return true;
    }

    private void circle(Canvas c,String name,float r,String label,int accent) {
        PointF p=center(name);
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(name.equals(dragged) ? 0xffe8dfc9 : pressed.contains(name) ? 0xaae8dfc9 : 0x4230394c);
        c.drawCircle(p.x,p.y,r,paint);
        paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(3); paint.setColor(accent);
        c.drawCircle(p.x,p.y,r,paint);
        paint.setStyle(Paint.Style.FILL); paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setTextSize(label.length()>2 ? 19 : 33); paint.setTextAlign(Paint.Align.CENTER);
        c.drawText(label,p.x,p.y-(paint.ascent()+paint.descent())/2,paint);
    }
    private void rectangle(Canvas c,String name,float width,String label) {
        PointF p=center(name);
        // The touchpad button presses "touchpad_right" (right-side click, opens the pause menu),
        // not "touchpad", so highlight it from that signal too.
        boolean lit=pressed.contains(name) ||
            (name.equals("touchpad") && pressed.contains("touchpad_right"));
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(name.equals(dragged) ? 0xffe8dfc9 : lit ? 0xaae8dfc9 : 0x4230394c);
        c.drawRoundRect(p.x-width/2,p.y-25,p.x+width/2,p.y+25,14,14,paint);
        paint.setStyle(Paint.Style.STROKE); paint.setColor(0xbbc6ad76); paint.setStrokeWidth(2);
        c.drawRoundRect(p.x-width/2,p.y-25,p.x+width/2,p.y+25,14,14,paint);
        paint.setStyle(Paint.Style.FILL); paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setTextSize(19); paint.setTextAlign(Paint.Align.CENTER);
        c.drawText(label,p.x,p.y-(paint.ascent()+paint.descent())/2,paint);
    }
    /**
     * inFAMOUS-style action buttons customized for GoW III. The drawing
     * depicts chains, blades, shield, jump and magic. Captions are ONLY
     * physical button IDs (L1/L2/R1/R2/L3/R3/△/○/×/□), for combos/QTEs.
     */
    private void gowAction(Canvas c,String name,String legend,float radius) {
        PointF p=center(name);float s=size(name);
        c.save();c.scale(s,s,p.x,p.y);
        boolean down=pressed.contains(name) || (name.equals("rage") && pressed.contains("l3") && pressed.contains("r3"));
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(name.equals(dragged) ? 0xaae2a46d : down ? 0xaab32a22 : 0x70140912);
        c.drawCircle(p.x,p.y,radius,paint);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(name.equals("r2") ? 3f : 1.8f);
        paint.setColor(down ? 0xffffd5a2 : 0xccdbac7c);
        c.drawCircle(p.x,p.y,radius,paint);
        c.save();c.translate(p.x,p.y);
        paint.setColor(0xffe8d2bb);
        paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(3f);
        Bitmap icon=actionIcons.get(name);
        if (icon!=null) {
            paint.setStyle(Paint.Style.FILL);paint.setColor(0xffffffff);paint.setFilterBitmap(true);
            float extent=radius-5f;
            c.drawBitmap(icon,null,new RectF(-extent,-extent,extent,extent),paint);
        } else if (name.equals("options")) {
            c.drawLine(-8,-12,-8,12,paint);c.drawLine(8,-12,8,12,paint);
        } else if (name.equals("touchpad")) {
            c.drawRoundRect(-16,-11,16,11,4,4,paint);
            c.drawRoundRect(-9,-5,23,17,4,4,paint);
        } else if (name.equals("weapons")) {
            c.drawLine(-17,0,17,0,paint);c.drawLine(0,-17,0,17,paint);
            c.drawCircle(0,0,21,paint);
        }
        c.restore();
        if (preferences.getBoolean("overlay_button_labels",true) &&
            !legend.isEmpty()) {
            paint.setStyle(Paint.Style.FILL);paint.setTextAlign(Paint.Align.CENTER);
            paint.setTypeface(Typeface.DEFAULT_BOLD);paint.setColor(0xeef0d9c4);
            paint.setTextSize(14f);
            c.drawText(legend,p.x,p.y+radius+17f,paint);
        }
        c.restore();
    }
    private void drawStick(Canvas c,String name) {
        PointF p=layoutCenter(name);float s=size(name);
        boolean active=false;
        for(int i=0;i<controls.size();i++) if(name.equals(controls.valueAt(i))) active=true;
        c.save();c.scale(s,s,p.x,p.y);
        paint.setStyle(Paint.Style.STROKE);paint.setColor(0x88dbac7c);
        paint.setStrokeWidth(2f);c.drawCircle(p.x,p.y,66,paint);
        paint.setStyle(Paint.Style.FILL);paint.setColor(0x66b83d27);
        {
            float x=p.x,y=p.y;
            for(int i=0;i<controls.size();i++)if(name.equals(controls.valueAt(i))) {
                PointF q=positions.get(controls.keyAt(i));
                if(q!=null){PointF origin=center(name);
                    x=p.x+Math.max(-26,Math.min(26,q.x-origin.x));
                    y=p.y+Math.max(-26,Math.min(26,q.y-origin.y));}
                break;
            }
            c.drawCircle(x,y,22,paint);
        }
        c.restore();
    }
    private void drawDodge(Canvas c) {
        // Same circular ring, dark fill and moving red thumb as the left stick.
        // The arrows describe direction without a text panel over gameplay.
        drawStick(c,"rightstick");
        PointF p=layoutCenter("rightstick");float s=size("rightstick");
        c.save();c.scale(s,s,p.x,p.y);c.translate(p.x,p.y);
        paint.setStyle(Paint.Style.STROKE);paint.setColor(0xccdbac7c);paint.setStrokeWidth(2.2f);
        for(int i=0;i<4;i++) {
            c.save();c.rotate(i*90f);
            c.drawLine(-5,-45,0,-51,paint);c.drawLine(0,-51,5,-45,paint);
            c.restore();
        }
        c.restore();
    }
    float[][] hudExclusions() {
        if(getVisibility()!=VISIBLE || getWidth()<=0 || getHeight()<=0) return new float[0][];
        java.util.ArrayList<float[]> result=new java.util.ArrayList<>();float factor=scale();
        for(String name:NAMES) {
            if(!editing && !saveDialogMode && !weaponsOpen && (name.equals("up") || name.equals("left") ||
                name.equals("right") || name.equals("down"))) continue;
            if(saveDialogMode && !dialogControlAllowed(name)) continue;
            PointF at=layoutCenter(name);
            float radius=(stick(name)?66:44)*size(name);
            float label=stick(name)?0:20*size(name);
            result.add(new float[]{(at.x-radius)*factor,(at.y-radius)*factor,
                (at.x+radius)*factor,(at.y+radius+label)*factor});
        }
        return result.toArray(new float[0][]);
    }
    @Override protected void onDraw(Canvas c) {
        super.onDraw(c);
        c.save();c.translate(offsetX(),offsetY());c.scale(scale(),scale());
        final boolean modal=saveDialogActive();
        // No enormous legacy buttons and no long action captions.
        if (!modal || editing) {
            gowAction(c,"l2","L2",34);
            gowAction(c,"l1","L1",34);
            gowAction(c,"r1","R1",34);
            gowAction(c,"r2","R2",41);
            gowAction(c,"options","",29);
            gowAction(c,"touchpad","",27);
        }
        if (modal || editing || weaponsOpen) {
        circle(c,"up",25,"▲",0xffc6ad76);
        circle(c,"left",25,"◀",0xffc6ad76);
        circle(c,"right",25,"▶",0xffc6ad76);
        circle(c,"down",25,"▼",0xffc6ad76);
        }
        if (!modal || editing) {
            gowAction(c,"triangle","△",33);
            gowAction(c,"square","□",33);
        }
        gowAction(c,"circle","○",33);
        gowAction(c,"cross","×",39);
        if (!modal || editing) {
            drawStick(c,"leftstick");drawDodge(c);
            gowAction(c,"rage","L3 + R3",37);gowAction(c,"weapons","",29);
        }
        if (editing) {
            paint.setStyle(Paint.Style.FILL);paint.setColor(0xdd15171d);
            float doneX=getWidth()/scale()/2;
            c.drawRoundRect(doneX-92,6,doneX+92,64,13,13,paint);
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2);
            paint.setColor(0xffc6ad76);c.drawRoundRect(doneX-92,6,doneX+92,64,13,13,paint);
            paint.setStyle(Paint.Style.FILL);paint.setTextSize(19);
            paint.setTextAlign(Paint.Align.CENTER);
            c.drawText(UiText.get(getContext(),"DONE"),doneX,35-(paint.ascent()+paint.descent())/2,paint);
        }
        c.restore();
        // SaveDataDialog opens asynchronously in the native game thread.  A
        // touch overlay otherwise redraws only after pad interactions, so
        // the new modal marker is never observed and shoulder/stick buttons
        // remain drawn over the Load panel. Poll at 5 Hz, not per-frame.
        if (getWindowToken() != null && getVisibility() == VISIBLE)
            postInvalidateDelayed(200);
    }
}
