package ro.cobrabm.fexdroid;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Canvas;
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
        "leftstick","l3","r3","rightstick"
    };
    // GoW III mobile layout based on the inFAMOUS Android action-pad design.
    // Guard the first 125 virtual pixels for landscape status bars/cutouts.
    // D-pad switches weapons/magic; right stick handles evasion; L3+R3 stays
    // visible for Rage. Legacy generic layouts are kept under their old keys.
    private static final float[][] DEFAULT={
        {152,184},{264,184},{640,176},{790,176},{1014,184},{1126,184},
        {138,348},{86,402},{190,402},{138,456},
        {1035,339},{1130,425},{1035,511},{940,425},
        {312,581},{441,620},{839,620},{854,581}
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
    private PointF moveOrigin,dodgeOrigin;
    private float pinchStartDistance,pinchStartSize;
    private String key(String axis,String name) { return "gow3_mobile_v2_"+axis+"_"+name; }
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
        setContentDescription("On-screen PlayStation controller");
    }
    private PointF center(String name) {
        if (!editing && "leftstick".equals(name) && moveOrigin!=null) return moveOrigin;
        if (!editing && "rightstick".equals(name) && dodgeOrigin!=null) return dodgeOrigin;
        return centers.get(name);
    }
    // The 1280x720 layout drawn at one scale in the centred 16:9 area, as the game (MainActivity):
    // round on any screen shape. Controls may be dragged into the bars around it.
    private float scale() { return Math.max(1e-3f,Math.min(getWidth()/1280f,getHeight()/720f)); }
    private float offsetX() { return (getWidth()-1280f*scale())/2f; }
    private float offsetY() { return (getHeight()-720f*scale())/2f; }
    private float layoutX(MotionEvent e,int index) { return (e.getX(index)-offsetX())/scale(); }
    private float layoutY(MotionEvent e,int index) { return (e.getY(index)-offsetY())/scale(); }
    private static float distance(float x,float y,PointF p) { return (float)Math.hypot(x-p.x,y-p.y); }
    private static boolean stick(String name) { return name.equals("leftstick") || name.equals("rightstick"); }
    private static boolean rectangle(String name) {
        return name.equals("l1") || name.equals("l2") || name.equals("r1") ||
               name.equals("r2") || name.equals("touchpad") || name.equals("options");
    }
    private PointF dpadCenter() {
        PointF u=center("up"),l=center("left"),r=center("right"),d=center("down");
        return new PointF((u.x+l.x+r.x+d.x)/4f,(u.y+l.y+r.y+d.y)/4f);
    }
    private String hit(float x,float y) {
        final boolean save=saveDialogActive();
        PointF dpad=dpadCenter();
        if (!editing && distance(x,y,dpad)<112 && distance(center("up").x,center("up").y,dpad)<115 &&
            distance(center("left").x,center("left").y,dpad)<115 &&
            distance(center("right").x,center("right").y,dpad)<115 &&
            distance(center("down").x,center("down").y,dpad)<115) return "dpad";
        String winner=null; float best=Float.MAX_VALUE;
        for (String name:NAMES) {
            if (save && !dialogControlAllowed(name)) continue;
            PointF p=center(name);
            float dx=Math.abs(x-p.x),dy=Math.abs(y-p.y);
            float scale=size(name);
            boolean inside=rectangle(name) ? dx<(name.equals("touchpad") ? 58 : 50)*scale && dy<36*scale
                    : distance(x,y,p)<(stick(name) ? 42 : name.equals("l3") || name.equals("r3") ? 34 : 44)*scale;
            if (inside && distance(x,y,p)<best) { best=distance(x,y,p); winner=name; }
        }
        if (winner!=null || editing || save) return winner;
        // Floating thumb zones like the inFAMOUS mobile controls. On GoW III
        // the right stick must remain held for the directional evade.
        if (x<465 && y>480) return "leftstick";
        if (x>635 && y>470) return "rightstick";
        return null;
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
            } else pressed.add(control);
        }
        if (mouse!=mouseDown) { XInput.button(1,mouse); mouseDown=mouse; }
        pad.virtual(pressed,lx,ly,rx,ry,left,right,l2,r2);
        invalidate();
    }
    void release() {
        controls.clear(); positions.clear(); moveOrigin=null; dodgeOrigin=null; publish();
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
        editor.apply(); release(); invalidate();
    }

    @Override public boolean onTouchEvent(MotionEvent e) {
        int action=e.getActionMasked(),at=e.getActionIndex(),id=e.getPointerId(at);
        if (editing) {
            if (action==MotionEvent.ACTION_CANCEL) { editPointer=-1; dragged=null; return true; }
            if (action==MotionEvent.ACTION_DOWN) {
                float x=layoutX(e,at),y=layoutY(e,at);
                if (x>548 && x<732 && y>97 && y<159) { finishEdit(); return true; }
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
                        pinchStartSize*(float)Math.hypot(dx,dy)/pinchStartDistance)));
                } else {
                    int index=e.findPointerIndex(editPointer);
                    if (index>=0) center(dragged).set(
                        Math.max(54,Math.min(1226,layoutX(e,index))),
                        Math.max(130,Math.min(666,layoutY(e,index))));
                }
                invalidate();
            } else if (action==MotionEvent.ACTION_POINTER_UP) {
                pinchStartDistance=0f;
                if (dragged!=null)
                    preferences.edit().putFloat(key("size",dragged),size(dragged)).apply();
            } else if (action==MotionEvent.ACTION_UP && id==editPointer && dragged!=null) {
                PointF p=center(dragged);
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
            if (name==null && !mouseEnabled) return true;
            controls.put(id,name==null ? "mouse" : name);
            positions.put(id,new PointF(x,y));
            if ("leftstick".equals(name)) moveOrigin=new PointF(x,y);
            if ("rightstick".equals(name)) dodgeOrigin=new PointF(x,y);
        } else if (action==MotionEvent.ACTION_UP || action==MotionEvent.ACTION_POINTER_UP) {
            String released=controls.get(id);
            controls.remove(id); positions.remove(id);
            if ("leftstick".equals(released)) moveOrigin=null;
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
        boolean down=pressed.contains(name);
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
        switch(name) {
            case "l1": // shield / block
                android.graphics.Path shield=new android.graphics.Path();
                shield.moveTo(0,-20);shield.lineTo(17,-12);shield.lineTo(13,9);
                shield.lineTo(0,21);shield.lineTo(-13,9);shield.lineTo(-17,-12);
                shield.close();c.drawPath(shield,paint);break;
            case "l2": // magic rune
                c.drawCircle(0,0,16,paint);c.drawCircle(0,0,5,paint);
                c.drawLine(-23,0,-12,0,paint);c.drawLine(12,0,23,0,paint);break;
            case "r1": // crossed chained blades
                c.drawLine(-17,-19,16,18,paint);c.drawLine(16,-19,-17,18,paint);
                c.drawLine(-20,-13,-12,-21,paint);c.drawLine(12,-21,20,-13,paint);break;
            case "r2": // spark / item
                c.drawLine(0,-21,-8,-1,paint);c.drawLine(-8,-1,5,-1,paint);
                c.drawLine(5,-1,-3,21,paint);c.drawLine(-3,21,15,-7,paint);break;
            case "triangle": // two overhead blades
                c.drawLine(-16,18,0,-20,paint);c.drawLine(16,18,0,-20,paint);
                c.drawLine(-19,11,-11,15,paint);c.drawLine(19,11,11,15,paint);break;
            case "square": // chained quick-strike slashes
                c.drawLine(-20,16,-4,-17,paint);c.drawLine(-4,16,12,-17,paint);
                c.drawLine(12,16,20,-4,paint);break;
            case "circle": // grapple chain
                c.drawCircle(-8,0,10,paint);c.drawCircle(8,0,10,paint);
                c.drawLine(-18,0,-12,-8,paint);c.drawLine(12,8,18,0,paint);break;
            case "cross": // jump
                c.drawLine(0,19,0,-20,paint);c.drawLine(0,-20,-15,-3,paint);
                c.drawLine(0,-20,15,-3,paint);c.drawLine(-16,20,16,20,paint);break;
            case "options":
                c.drawLine(-11,-16,-11,16,paint);c.drawLine(11,-16,11,16,paint);break;
            case "touchpad":c.drawRoundRect(-22,-14,22,14,6,6,paint);break;
            default:
                paint.setStyle(Paint.Style.FILL);
                paint.setTypeface(Typeface.DEFAULT_BOLD);
                paint.setTextAlign(Paint.Align.CENTER);
                paint.setTextSize(21);
                c.drawText(name.equals("l3") ? "L3" : "R3",0,7,paint);
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
        PointF p=center(name);float s=size(name);
        boolean active=false;
        for(int i=0;i<controls.size();i++) if(name.equals(controls.valueAt(i))) active=true;
        c.save();c.scale(s,s,p.x,p.y);
        paint.setStyle(Paint.Style.STROKE);paint.setColor(0x88dbac7c);
        paint.setStrokeWidth(2f);c.drawCircle(p.x,p.y,active||editing ? 47 : 27,paint);
        paint.setStyle(Paint.Style.FILL);paint.setColor(0x66b83d27);
        if (active||editing) {
            float x=p.x,y=p.y;
            for(int i=0;i<controls.size();i++)if(name.equals(controls.valueAt(i))) {
                PointF q=positions.get(controls.keyAt(i));
                if(q!=null){x=p.x+Math.max(-26,Math.min(26,q.x-p.x));
                            y=p.y+Math.max(-26,Math.min(26,q.y-p.y));}
                break;
            }
            c.drawCircle(x,y,22,paint);
        } else c.drawCircle(p.x,p.y,7,paint);
        c.restore();
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
        circle(c,"up",25,"▲",0xffc6ad76);
        circle(c,"left",25,"◀",0xffc6ad76);
        circle(c,"right",25,"▶",0xffc6ad76);
        circle(c,"down",25,"▼",0xffc6ad76);
        if (!modal || editing) {
            gowAction(c,"triangle","△",33);
            gowAction(c,"square","□",33);
        }
        gowAction(c,"circle","○",33);
        gowAction(c,"cross","×",39);
        if (!modal || editing) {
            drawStick(c,"leftstick");drawStick(c,"rightstick");
            gowAction(c,"l3","L3",26);gowAction(c,"r3","R3",26);
        }
        if (editing) {
            paint.setStyle(Paint.Style.FILL);paint.setColor(0xdd15171d);
            c.drawRoundRect(548,100,732,158,13,13,paint);
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2);
            paint.setColor(0xffc6ad76);c.drawRoundRect(548,100,732,158,13,13,paint);
            paint.setStyle(Paint.Style.FILL);paint.setTextSize(19);
            paint.setTextAlign(Paint.Align.CENTER);
            c.drawText("DONE",640,129-(paint.ascent()+paint.descent())/2,paint);
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
