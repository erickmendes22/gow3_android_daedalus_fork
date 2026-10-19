package ro.cobrabm.fexdroid;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputFilter;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** God of War III-only Android player. Keeps the game surface alive beneath its sliding drawer. */
public final class GameActivity extends Activity {
    /** The app's files (application id com.gow3.android), its Linux rootfs and gow3port runtime.
     *  Rootfs programs are launched through the in-tree loader when their PT_INTERP slot cannot
     *  hold the app-private path. */
    private String FILES, ROOT, BASE;
    /** The game (e.g. CUSA01740, with eboot.bin) in shared storage, chosen by the player. */
    private String gameDir;
    /** An optional update folder (e.g. CUSA01740-patch): laid over the game at start. */
    private String updateDir;
    private static final int REQUEST_FOLDER=1, REQUEST_STORAGE=2;
    private SurfaceHolder pendingHolder;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private FrameLayout screen;
    private SurfaceView surface;
    private View scrim, handle;
    private LinearLayout drawer;
    private LinearLayout drawerItems;
    private TextView status;
    private View resume;
    private LinearLayout gameSettingsItem, cheatsItem, graphicsItem, controllerItem, swapFaceItem;
    private TouchControllerOverlay controllerOverlay;
    private PerfHudOverlay perfHud;
    private LinearLayout perfHudItem, frameGenItem;
    private PadBridge pad;
    private AudioBridge audio;
    private volatile Process xvfb, game;
    private volatile int shmid=-1;
    private volatile boolean destroyed;
    private boolean drawerOpen, displayOnly, startingX, hadError, swipeConsumed;
    private float touchX, touchY;
    private boolean edgeGesture, imeOpen, imePolling;
    private final AtomicBoolean imeAnswered=new AtomicBoolean();
    private EditText imeField;
    private AlertDialog imeDialog;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        FILES=getFilesDir().getAbsolutePath();
        ROOT=FILES+"/rootfs"; BASE=FILES+"/gow3port";
        gameDir=getSharedPreferences("gow3",MODE_PRIVATE).getString("game_dir",null);
        updateDir=getSharedPreferences("gow3",MODE_PRIVATE).getString("update_dir",null);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (Build.VERSION.SDK_INT>=28) {
            WindowManager.LayoutParams attrs=getWindow().getAttributes();
            attrs.layoutInDisplayCutoutMode=WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            getWindow().setAttributes(attrs);
        }
        displayOnly="x".equals(getIntent().getStringExtra("action"));
        pad=new PadBridge(new File(BASE,"android-pad.state"));
        pad.setSwapFaceButtons(getSharedPreferences("gow3",MODE_PRIVATE).getBoolean("swap_square_triangle",false));
        audio=new AudioBridge(new File(BASE,"audio.fifo"));
        buildScreen();
        immersive();
    }

    private boolean bionicRuntime() { return "com.gow3.android.bionic".equals(getPackageName()); }

    private boolean runtimeReady;

    /** Installation must finish before choosing presentation or starting native bridges. */
    private void startRuntime(SurfaceHolder holder) {
        if (destroyed || !holder.getSurface().isValid()) return;
        if (runtimeReady) {
            if (bionicRuntime()) startBionic(holder);
            else if (shmid>=0) attach(holder);
            else if (!startingX) { startingX=true; worker.execute(() -> startX(holder)); }
            return;
        }
        if (startingX) return;
        startingX=true;
        worker.execute(() -> {
            try {
                boolean installed=RuntimeInstaller.ensure(GameActivity.this, new File(FILES),
                    message -> main.post(() -> status.setText(UiText.get(GameActivity.this, message))));
                android.util.Log.i("God of War III","runtime installed="+installed);
                main.post(() -> {
                    startingX=false;
                    if (destroyed) return;
                    runtimeReady=true;
                    startRuntime(surface.getHolder());
                });
            } catch (Exception ex) {
                main.post(() -> startingX=false);
                error(ex.toString());
            }
        });
    }

    private void startBionic(SurfaceHolder holder) {
        if (destroyed || !holder.getSurface().isValid()) return;
        try {
            if (Build.VERSION.SDK_INT < 30) throw new java.io.IOException("Bionic runtime requires Android 11 or newer");
            String result=Gow3Present.start(holder,BASE+"/present.sock","1".equals(setting("android_fullscreen")));
            if (!result.startsWith("bridge running:")) throw new java.io.IOException(result);
            if (!displayOnly && game==null && !startingX) {
                startingX=true;
                worker.execute(() -> {
                    if (audio!=null) audio.start();
                    if (audio==null || !audio.awaitReady(5000)) { error("Android audio bridge could not start"); return; }
                    startGame();
                });
            }
            pollFrames();
            if (!imePolling) { imePolling=true; pollIme(); }
        } catch (Exception ex) { error(ex.toString()); }
    }

    private int dp(float n) { return Math.round(n*getResources().getDisplayMetrics().density); }
    private TextView text(String value, int size, int color) {
        TextView t=new TextView(this); t.setText(UiText.get(this, value)); t.setTextSize(size); t.setTextColor(color); return t;
    }
    private FrameLayout.LayoutParams frame(int width,int height,int gravity) {
        return new FrameLayout.LayoutParams(width,height,gravity);
    }
    private void fitSurface(int width,int height) {
        if (width<=0 || height<=0) return;
        int w=width, h=height;
        if (!"1".equals(setting("android_fullscreen"))) {
            if ((long)w*9>(long)h*16) w=h*16/9; else h=w*9/16;
        }
        FrameLayout.LayoutParams p=(FrameLayout.LayoutParams)surface.getLayoutParams();
        if (p.width==w && p.height==h) return;
        p.width=w; p.height=h;
        // Not during the layout pass that reported the size.
        surface.post(() -> surface.setLayoutParams(p));
    }

    private void buildScreen() {
        screen=new FrameLayout(this); screen.setBackgroundColor(Color.BLACK);
        surface=new SurfaceView(this);
        screen.addView(surface,frame(-1,-1,Gravity.CENTER));
        // The game is 16:9: the largest 16:9 area of the screen, black bars around it (a foldable's
        // near-square inner screen, a tall cover screen). Refitted when folding or rotating.
        screen.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob) -> fitSurface(r-l,b-t));
        surface.getHolder().addCallback(new SurfaceHolder.Callback() {
            @Override public void surfaceCreated(SurfaceHolder h) {
                if (!hasGame()) {
                    pendingHolder=h;
                    error("Game folder is unavailable. Return to the launcher and choose it again.");
                } else startRuntime(h);
            }
            @Override public void surfaceChanged(SurfaceHolder h,int format,int w,int height) {}
            @Override public void surfaceDestroyed(SurfaceHolder h) { if (!bionicRuntime()) DisplayBridge.stop(); }
        });
        surface.setOnTouchListener((v,e) -> {
            if (shmid<0 || drawerOpen) return true;
            XInput.moveTo(Math.round(e.getX()*1280/Math.max(1,v.getWidth())),
                          Math.round(e.getY()*720/Math.max(1,v.getHeight())));
            if (e.getActionMasked()==MotionEvent.ACTION_DOWN) XInput.button(1,true);
            if (e.getActionMasked()==MotionEvent.ACTION_UP || e.getActionMasked()==MotionEvent.ACTION_CANCEL)
                XInput.button(1,false);
            return true;
        });
        status=text("Starting God of War III…",18,0xffc6ad76); status.setGravity(Gravity.CENTER);
        screen.addView(status,frame(-1,-1,Gravity.CENTER));
        status.setClickable(false);

        controllerOverlay=new TouchControllerOverlay(this,pad,!bionicRuntime() && "1".equals(setting("overlay_mouse")));
        controllerOverlay.setVisibility(controllerEnabled() ? View.VISIBLE : View.GONE);
        screen.addView(controllerOverlay,frame(-1,-1,Gravity.CENTER));
        // Upstream-style draggable HUD stays above the controller and below the drawer.
        perfHud=new PerfHudOverlay(this);
        screen.addView(perfHud,frame(-1,-1,Gravity.CENTER));
        perfHud.setActive(getSharedPreferences("gow3",MODE_PRIVATE)
                .getBoolean("performance_hud",false));

        handle=new View(this);
        GradientDrawable grip=new GradientDrawable(); grip.setColor(0x80c6ad76); grip.setCornerRadius(dp(4));
        handle.setBackground(grip); handle.setContentDescription("Open game menu");
        screen.addView(handle,frame(dp(4),dp(44),Gravity.LEFT|Gravity.CENTER_VERTICAL));
        handle.setOnClickListener(v -> openDrawer());

        scrim=new View(this); scrim.setBackgroundColor(0x99000000);
        scrim.setVisibility(View.GONE); scrim.setOnClickListener(v -> closeDrawer());
        screen.addView(scrim,frame(-1,-1,Gravity.FILL));

        drawer=new LinearLayout(this); drawer.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable panel=new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
            new int[]{0xff1b1d24,0xff121318});
        drawer.setBackground(panel);
        drawer.setElevation(dp(16)); drawer.setVisibility(View.GONE);
        drawerItems=new LinearLayout(this); drawerItems.setOrientation(LinearLayout.VERTICAL);
        drawerItems.setPadding(dp(14),dp(20),dp(14),dp(16));
        android.widget.ScrollView drawerScroll=new android.widget.ScrollView(this);
        drawerScroll.setFillViewport(false);
        drawerScroll.addView(drawerItems);
        // A thin gold edge on the game side.
        LinearLayout body=new LinearLayout(this);
        body.addView(drawerScroll,new LinearLayout.LayoutParams(0,-1,1));
        View edge=new View(this); edge.setBackgroundColor(0x55c6ad76);
        body.addView(edge,new LinearLayout.LayoutParams(dp(1),-1));
        drawer.addView(body,new LinearLayout.LayoutParams(-1,0,1));

        TextView hint=text("Swipe left or press A to return",12,0xff8e9097);
        hint.setPadding(dp(10),dp(2),0,dp(6));
        drawerItems.addView(hint,new LinearLayout.LayoutParams(-1,-2));

        section("Game");
        resume=menuItem("ic_play","Resume game",null,() -> closeDrawer());
        /* Game settings 与 Cheats 两个入口已隐藏（对应 SettingsDialog.showGame()/showCheats() 也已
         * 注释掉）：它们写的 ini 键在本仓库的启动链路里没有消费方，作弊更是根本没装 hook——Android
         * 走 FEXCore JIT，probe.c 的 install_cheats() 被 `#if defined(GUEST_CPU_NATIVE)` 编译掉了。
         * 留着入口只会让玩家以为改了有用。接通后把下面两段取消注释即可。
        gameSettingsItem=menuItem("ic_settings","Game settings","",() -> {
            closeDrawer();
            new SettingsDialog(this,new File(BASE,"gow3.ini"),this::restartGame).showGame();
        });
        cheatsItem=menuItem("ic_cheats","Cheats","",() -> {
            closeDrawer();
            new SettingsDialog(this,new File(BASE,"gow3.ini"),this::restartGame).showCheats();
        });
         */
        menuItem("ic_refresh","Restart game","Unsaved progress is lost",() -> new AlertDialog.Builder(this)
            .setTitle(UiText.get(this, "Restart God of War III?")).setMessage(UiText.get(this, "Any unsaved progress will be lost."))
            .setNegativeButton(UiText.get(this, "Cancel"),null).setPositiveButton(UiText.get(this, "Restart"),(dialog,which) -> restartGame()).show());

        section("Graphics");
        // Graphics 入口只保留运行时真正消费的那几项：upscaler / preset / sharpen / sharpness /
        // show_fps / fps_limit。原来的 CPU 核心（thor_cpus）、特效（effect_*）、模型细节
        // （model_lod）在本仓库启动链路没有消费方，已在 SettingsDialog.show() 里注释掉。
        // fps_limit 的摘要取值域与 SettingsDialog.FPS_VALUES 和运行时 FPS_LIMITS
        // （30/60/120/240/0）对齐。
        graphicsItem=menuItem("ic_tune","Graphics settings","",() -> {
            closeDrawer();
            new SettingsDialog(this,new File(BASE,"gow3.ini"),this::restartGame).show();
        });

        if (bionicRuntime()) {
            frameGenItem=menuItem("ic_frames","Frame generation (Bloodframe)",
                "Off · 2x/3x/4x; changes apply live", this::chooseFrameGeneration);
        }
        perfHudItem=menuItem("ic_tune","Draggable FPS / GPU / CPU HUD","",() -> {
            boolean on=!getSharedPreferences("gow3",MODE_PRIVATE)
                    .getBoolean("performance_hud",false);
            getSharedPreferences("gow3",MODE_PRIVATE).edit()
                    .putBoolean("performance_hud",on).apply();
            if (perfHud!=null) perfHud.setActive(on);
            setDetail(perfHudItem,on ? "On" : "Off");
        });

        section("Controls");
        controllerItem=menuItem("ic_gamepad","On-screen controller","",() -> {
            boolean enabled=!controllerEnabled();
            getSharedPreferences("gow3",MODE_PRIVATE).edit().putBoolean("controller_overlay",enabled).apply();
            controllerOverlay.release();
            closeDrawer();
        });
        swapFaceItem=menuItem("ic_gamepad","Swap Square/Triangle","",() -> {
            boolean enabled=!getSharedPreferences("gow3",MODE_PRIVATE).getBoolean("swap_square_triangle",false);
            getSharedPreferences("gow3",MODE_PRIVATE).edit().putBoolean("swap_square_triangle",enabled).apply();
            pad.setSwapFaceButtons(enabled);
            setDetail(swapFaceItem,enabled ? "On" : "Off");
        });
        menuItem("ic_edit","Edit controller layout","Drag and resize the buttons",() -> {
            getSharedPreferences("gow3",MODE_PRIVATE).edit().putBoolean("controller_overlay",true).apply();
            closeDrawer();
            controllerOverlay.edit(null);
        });
        menuItem("ic_restore","Reset controller layout",null,() -> {
            controllerOverlay.resetLayout();
            closeDrawer();
        });

        menuItem("ic_exit","Quit game",null,() -> new AlertDialog.Builder(this)
            .setTitle(UiText.get(this, "Quit God of War III?")).setMessage(UiText.get(this, "Any unsaved progress will be lost."))
            .setNegativeButton(UiText.get(this, "Cancel"),null).setPositiveButton(UiText.get(this, "Quit"),(dialog,which) -> finish()).show());

        // The version, pinned under the scrolling menu.
        String version="";
        try { version=" "+getPackageManager().getPackageInfo(getPackageName(),0).versionName; }
        catch (Exception ignored) {}
        TextView about=text(getString(com.gow3.android.R.string.app_name)+version,12,0xff8e9097);
        about.setPadding(dp(24),dp(8),dp(14),dp(14));
        drawer.addView(about,new LinearLayout.LayoutParams(-1,-2));
        screen.addView(drawer,frame(dp(320),-1,Gravity.LEFT));
        setContentView(screen);
    }

    private void restartGame() {
        closeDrawer(); status.setText(UiText.get(this, "Restarting God of War III…")); status.setVisibility(View.VISIBLE);
        if (!runtimeReady) { startPending(); return; }
        worker.execute(() -> { stopGame(); startGame(); });
    }

    /** A small gold heading above a group of menu rows. */
    private void section(String name) {
        TextView t=text(name.toUpperCase(java.util.Locale.ROOT),11,0xffc6ad76);
        t.setLetterSpacing(0.15f); t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setPadding(dp(10),dp(16),0,dp(6));
        drawerItems.addView(t,new LinearLayout.LayoutParams(-1,-2));
    }

    /** A menu row: icon, title and an optional second line (null: none; "" filled by refreshDrawer).
     *  Focusable for the gamepad, with a gold highlight when focused or pressed. */
    private LinearLayout menuItem(String icon,String title,String detail,Runnable action) {
        LinearLayout row=new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL); row.setPadding(dp(10),dp(8),dp(10),dp(8));
        row.setFocusable(true); row.setClickable(true); row.setTag(action); row.setOnClickListener(v -> ((Runnable)row.getTag()).run());
        android.graphics.drawable.StateListDrawable states=new android.graphics.drawable.StateListDrawable();
        GradientDrawable lit=new GradientDrawable(); lit.setColor(0x33c6ad76); lit.setCornerRadius(dp(10));
        lit.setStroke(dp(1),0x99c6ad76);
        GradientDrawable pressed=new GradientDrawable(); pressed.setColor(0x44c6ad76); pressed.setCornerRadius(dp(10));
        states.addState(new int[]{android.R.attr.state_pressed},pressed);
        states.addState(new int[]{android.R.attr.state_focused},lit);
        states.addState(new int[]{},new android.graphics.drawable.ColorDrawable(0));
        row.setBackground(states);

        android.widget.ImageView image=new android.widget.ImageView(this);
        int id=getResources().getIdentifier(icon,"drawable",getPackageName());
        if (id!=0) image.setImageResource(id);
        LinearLayout.LayoutParams ip=new LinearLayout.LayoutParams(dp(24),dp(24)); ip.rightMargin=dp(14);
        row.addView(image,ip);

        LinearLayout texts=new LinearLayout(this); texts.setOrientation(LinearLayout.VERTICAL);
        TextView name=text(title,15,0xffe8dfc9);
        texts.addView(name);
        if (detail!=null) {
            TextView second=text(detail,12,0xff8e9097); second.setTag("detail");
            texts.addView(second);
        }
        row.addView(texts,new LinearLayout.LayoutParams(0,-2,1));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2); lp.bottomMargin=dp(2);
        row.setMinimumHeight(dp(48));
        drawerItems.addView(row,lp); return row;
    }
    private static void setDetail(LinearLayout row,String value) {
        TextView detail=row==null ? null : (TextView)row.findViewWithTag("detail");
        if (detail!=null) detail.setText(UiText.get(detail.getContext(), value));
    }
    /** 抽屉里的一行不可用时：不可点击、不可获焦（手柄/键盘导航会跳过它），并整体变灰。
     *  action 存在 row 的 tag 里，监听器保持挂着——setClickable(false) 会让点击不再分发，
     *  这样重新启用时不必再重挂一次监听器。 */
    private static void setRowEnabled(LinearLayout row,boolean on) {
        if (row==null) return;
        row.setClickable(on);
        row.setFocusable(on);
        row.setAlpha(on ? 1.0f : 0.4f);
    }
    /** The rows' second lines: the current settings, read when the drawer opens. */
    /** Upstream bloodframe: state file watched by the Bionic presenter every ~250ms.
     * The imported DLL is user-provided; no DLL is bundled into this APK. */
    private void chooseFrameGeneration() {
        final File dll=new File(BASE,"Lossless.dll");
        if (!dll.isFile() || dll.length()==0) {
            new AlertDialog.Builder(this).setTitle("Frame generation")
                    .setMessage("Import your Lossless.dll from Settings → General on the Home screen first.")
                    .setPositiveButton("OK",null).show();
            return;
        }
        final String[] modes={"Off (native frames)","Bloodframe 2x","Bloodframe 3x","Bloodframe 4x"};
        int now=getSharedPreferences("gow3",MODE_PRIVATE).getInt("framegen_multiplier",0);
        int checked=now>=2 && now<=4 ? now-1 : 0;
        new AlertDialog.Builder(this)
                .setTitle("Native frame generation")
                .setSingleChoiceItems(modes,checked,(dialog,which)->{
                    int mult=which==0 ? 0 : which+1;
                    if (writeFramegenState(mult)) {
                        getSharedPreferences("gow3",MODE_PRIVATE).edit()
                                .putInt("framegen_multiplier",mult).apply();
                        setDetail(frameGenItem,mult>=2 ? mult+"x (native)" : "Off");
                    } else {
                        new AlertDialog.Builder(this).setTitle("Frame generation")
                            .setMessage("Could not update framegen.state; no settings were changed.")
                            .setPositiveButton("OK",null).show();
                    }
                    dialog.dismiss();
                }).setNegativeButton("Cancel",null).show();
    }

    private boolean writeFramegenState(int multiplier) {
        final File file=new File(BASE,"framegen.state");
        final File tmp=new File(BASE,"framegen.state.tmp");
        try {
            if (!new File(BASE).isDirectory() && !new File(BASE).mkdirs()) return false;
            try (java.io.FileOutputStream output=new java.io.FileOutputStream(tmp)) {
                String data="multiplier="+(multiplier>=2 && multiplier<=4 ? multiplier : 0)+
                        "\nflow=0.80\nperformance=1\nfp16=1\n";
                output.write(data.getBytes(java.nio.charset.StandardCharsets.US_ASCII));
                output.getFD().sync();
            }
            return tmp.renameTo(file);
        } catch(Exception e) {
            tmp.delete();
            return false;
        }
    }

    private void refreshDrawer() {
        /* gameSettingsItem / cheatsItem 的摘要随上面两个入口一起注释掉了（接回来时一起放开）。
        java.util.List<String> game=new java.util.ArrayList<>();
        if (!"0".equals(setting("skip_network_choice"))) game.add("Offline start");
        if ("1".equals(setting("skip_intro"))) game.add("no intros");
        if ("1".equals(setting("debug_camera"))) game.add("free camera");
        if ("1".equals(setting("debug_menu"))) game.add("debug menu");
        setDetail(gameSettingsItem,game.isEmpty() ? "Online/offline screen shown" : String.join(" · ",game));
        java.util.List<String> cheats=new java.util.ArrayList<>();
        if ("1".equals(setting("cheat_health"))) cheats.add("infinite health");
        if ("1".equals(setting("cheat_item"))) cheats.add("infinite items");
        setDetail(cheatsItem,cheats.isEmpty() ? "Off" : String.join(" · ",cheats));
         */
        String upscaler="off".equals(setting("upscaler")) ? "No upscaling" : "FSR 3.1";
        String limit=setting("fps_limit");
        // 取值域与 SettingsDialog.FPS_VALUES 一致：只有 30/60/120/240 会按原值显示，0 是"不限制"，
        // 其余（键缺失、旧版遗留的 40/45）运行时 ParseFpsLimit 都当 0，所以回退显示 30。
        setDetail(graphicsItem,upscaler+" · "+("0".equals(limit) ? "no FPS limit"
            : (limit==null || !limit.matches("30|60|120|240") ? "30" : limit)+" FPS limit"));
        setDetail(controllerItem,controllerEnabled() ? "On" : "Off");
        setDetail(perfHudItem,getSharedPreferences("gow3",MODE_PRIVATE)
                .getBoolean("performance_hud",false) ? "On" : "Off");
        if (frameGenItem!=null) {
            int multiplier=getSharedPreferences("gow3",MODE_PRIVATE)
                    .getInt("framegen_multiplier",0);
            setDetail(frameGenItem,multiplier>=2 ? multiplier+"x (native)" : "Off");
        }
        setDetail(swapFaceItem,getSharedPreferences("gow3",MODE_PRIVATE).getBoolean("swap_square_triangle",false) ? "On" : "Off");
    }

    private void openDrawer() {
        if (drawerOpen) return;
        drawerOpen=true; controllerOverlay.release(); pad.reset(); if (!bionicRuntime()) XInput.button(1,false);
        refreshDrawer();
        controllerOverlay.setVisibility(View.GONE);
        handle.setVisibility(View.GONE);
        scrim.animate().cancel(); drawer.animate().cancel();
        scrim.setAlpha(0); scrim.setVisibility(View.VISIBLE); scrim.animate().alpha(1).setDuration(200).start();
        drawer.setTranslationX(-dp(320)); drawer.setVisibility(View.VISIBLE);
        drawer.animate().translationX(0).setDuration(220).start(); resume.requestFocus();
    }
    private void closeDrawer() {
        if (!drawerOpen) return;
        drawerOpen=false; pad.reset();
        controllerOverlay.setVisibility(controllerEnabled() ? View.VISIBLE : View.GONE);
        scrim.animate().cancel(); drawer.animate().cancel();
        scrim.animate().alpha(0).setDuration(180).withEndAction(() -> scrim.setVisibility(View.GONE)).start();
        drawer.animate().translationX(-dp(320)).setDuration(200)
            .withEndAction(() -> { drawer.setVisibility(View.GONE); handle.setVisibility(View.VISIBLE); surface.requestFocus(); }).start();
        immersive();
    }

    private void immersive() {
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN |
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY |
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        if (Build.VERSION.SDK_INT>=30) {
            getWindow().setDecorFitsSystemWindows(false);
            WindowInsetsController c=getWindow().getInsetsController();
            if (c!=null) {
                c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                c.hide(WindowInsets.Type.systemBars());
            }
        }
    }
    @Override public void onWindowFocusChanged(boolean focus) {
        super.onWindowFocusChanged(focus);
        if (focus) immersive(); else if (pad!=null) pad.reset();
    }
    @Override public void onBackPressed() { if (drawerOpen) closeDrawer(); else openDrawer(); }

    @Override public boolean dispatchTouchEvent(MotionEvent e) {
        if (e.getActionMasked()==MotionEvent.ACTION_DOWN) {
            swipeConsumed=false;
            touchX=e.getX(); touchY=e.getY();
            edgeGesture=!drawerOpen && touchX<dp(28);
        }
        if (swipeConsumed) return true;
        if (e.getActionMasked()==MotionEvent.ACTION_MOVE) {
            float dx=e.getX()-touchX, dy=e.getY()-touchY;
            if (edgeGesture && dx>dp(40) && Math.abs(dy)<dp(90)) {
                openDrawer(); edgeGesture=false; swipeConsumed=true; return true;
            }
            if (drawerOpen && dx< -dp(70) && Math.abs(dy)<dp(90)) {
                MotionEvent cancel=MotionEvent.obtain(e); cancel.setAction(MotionEvent.ACTION_CANCEL);
                super.dispatchTouchEvent(cancel); cancel.recycle();
                closeDrawer(); swipeConsumed=true; return true;
            }
        }
        if (edgeGesture) {
            if (e.getActionMasked()==MotionEvent.ACTION_UP) { edgeGesture=false; openDrawer(); }
            return true;
        }
        return super.dispatchTouchEvent(e);
    }

    @Override public boolean dispatchKeyEvent(KeyEvent e) {
        int code=e.getKeyCode();
        if (code==KeyEvent.KEYCODE_BACK || code==KeyEvent.KEYCODE_BUTTON_MODE) {
            if (e.getAction()==KeyEvent.ACTION_UP) onBackPressed(); return true;
        }
        if (drawerOpen) {
            if (code==KeyEvent.KEYCODE_BUTTON_B || e.getScanCode()==305) {
                if (e.getAction()==KeyEvent.ACTION_UP) closeDrawer(); return true;
            }
            if (code==KeyEvent.KEYCODE_BUTTON_A || e.getScanCode()==304) {
                if (e.getAction()==KeyEvent.ACTION_UP && getCurrentFocus()!=null) getCurrentFocus().performClick();
                return true;
            }
            return super.dispatchKeyEvent(e);
        }
        if (imeGamepad(e)) return true;
        if (pad.key(e)) return true;
        if (shmid>=0 && e.getScanCode()>0 && e.getScanCode()+8<=255) {
            XInput.key(e.getScanCode()+8,e.getAction()==KeyEvent.ACTION_DOWN); return true;
        }
        return super.dispatchKeyEvent(e);
    }
    @Override public boolean dispatchGenericMotionEvent(MotionEvent e) {
        if (drawerOpen && e.isFromSource(android.view.InputDevice.SOURCE_JOYSTICK)) return true;
        return pad.motion(e) || super.dispatchGenericMotionEvent(e);
    }
    private boolean controllerEnabled() {
        return getSharedPreferences("gow3",MODE_PRIVATE).getBoolean("controller_overlay",false);
    }
    @Override protected void onPause() {
        if (controllerOverlay!=null) controllerOverlay.release();
        if (pad!=null) pad.reset();
        if (audio!=null) audio.pause();
        super.onPause();
    }
    @Override protected void onResume() { super.onResume(); if (audio!=null) audio.resume(); }
    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        // Deterministic UI checks over ADB, using the same handlers as the actual controls.
        String action=intent.getStringExtra("ui_action");
        if ("open-menu".equals(action)) openDrawer();
        if ("close-menu".equals(action)) closeDrawer();
    }

    private Process process(String... args) throws java.io.IOException {
        ProcessBuilder b=new ProcessBuilder(args).redirectErrorStream(true);
        Map<String,String> env=b.environment(); env.clear();
        String target=args.length>1 && args[0].equals(ROOT+"/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1") ? args[1] : args[0];
        env.put("PATH",ROOT+"/usr/bin:"+ROOT+"/bin:/system/bin");
        env.put("HOME",FILES+"/home/gow3port"); env.put("LANG","C.UTF-8");
        env.put("TMPDIR",ROOT+"/tmp"); env.put("XDG_RUNTIME_DIR",ROOT+"/tmp");
        env.put("FXD_FILES",FILES); env.put("FXD_ROOT",ROOT); env.put("GOW3_ANDROID_INPUT","1");
        env.put("GOW3_LANGUAGE", UiText.gameLanguage(this));
        if (gameDir!=null) env.put("GOW3_GAME_DIR",gameDir);
        if (updateDir!=null) env.put("GOW3_PATCH_DIR",updateDir);
        if (bionicRuntime()) {
            GpuDriverManager.configureEnvironment(this,env);
            env.put("GOW3_SCREEN_W","1280"); env.put("GOW3_SCREEN_H","720");
            env.put("PATH","/system/bin"); env.put("TMPDIR",BASE+"/tmp"); env.put("XDG_RUNTIME_DIR",BASE+"/tmp");
            env.put("LD_LIBRARY_PATH",BASE+"/arm64/lib:"+BASE+"/arm64/python/lib");
            env.put("GOW3_PRESENT_SOCKET",BASE+"/present.sock");
            env.put("GOW3_DISPLAY_HZ",String.valueOf(Math.round(getWindowManager().getDefaultDisplay().getRefreshRate())));
            return b.start();
        }
        // Keep native port libraries and rootfs libraries visible to the explicit rootfs loader.
        env.put("LD_LIBRARY_PATH",BASE+"/arm64/lib:"+ROOT+"/usr/lib/aarch64-linux-gnu:"+ROOT+"/usr/lib");
        // Its libc emulates SysV shared memory through fxshmd (started below).
        env.put("FXD_SHM_SOCKET",ROOT+"/tmp/.fxshm/sock");
        env.put("GOW3_LANGUAGE", UiText.gameLanguage(this));
        if (gameDir!=null) env.put("GOW3_GAME_DIR",gameDir);
        if (updateDir!=null) env.put("GOW3_PATCH_DIR",updateDir);
        if (target.endsWith("/Xvfb")) env.put("LD_PRELOAD",ROOT+"/usr/lib/fexdroid/libfxpath.so");
        env.put("LIBGL_DRIVERS_PATH",ROOT+"/usr/lib/aarch64-linux-gnu/dri");
        return b.start();
    }
    private void startX(SurfaceHolder holder) {
        try {
            if (audio!=null) audio.start();
            if (audio==null || !audio.awaitReady(5000))
                throw new java.io.IOException("Android audio bridge did not become ready; see logcat for details.");
            if (!new File(ROOT,"usr/bin/Xvfb").canExecute() ||
                    !new File(BASE,"arm64/bin/gow3-probe").canExecute() ||
                    !new File(BASE,"run-gow3.sh").isFile())
                throw new java.io.IOException("The God of War III runtime is missing. Install the runtime bundle.");
            new File(FILES,"home/gow3port").mkdirs();
            try (PrintWriter passwd=new PrintWriter(new File(ROOT,"etc/passwd"));
                 PrintWriter group=new PrintWriter(new File(ROOT,"etc/group"))) {
                int uid=android.os.Process.myUid();
                passwd.println("root:x:0:0:root:/root:/bin/sh");
                passwd.println("user:x:"+uid+":"+uid+":God of War III:"+FILES+"/home/gow3port:"+ROOT+"/bin/sh");
                group.println("root:x:0:"); group.println("user:x:"+uid+":");
            }
            new File(ROOT,"tmp/.X0-lock").delete(); new File(ROOT,"tmp/.X11-unix/X0").delete();
            // The shared memory daemon (Xvfb's frame, the display bridge): forks itself and stays.
            Process shmd=process(ROOT+"/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1",
                ROOT+"/usr/libexec/fxshmd","--dir",ROOT+"/tmp/.fxshm");
            shmd.waitFor();
            xvfb=process(ROOT+"/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1",
                ROOT+"/usr/bin/Xvfb",":0","-screen","0","1280x720x24",
                "-shmem","-ac","-nolisten","tcp","-pn");
            Pattern ready=Pattern.compile("screen 0 shmid (\\d+)");
            BufferedReader r=new BufferedReader(new InputStreamReader(xvfb.getInputStream()));
            {
                String line;
                while ((line=r.readLine())!=null && !destroyed) {
                    android.util.Log.i("God of War III-X11",line);
                    Matcher m=ready.matcher(line);
                    if (m.find()) {
                        shmid=Integer.parseInt(m.group(1));
                        main.post(() -> attach(holder));
                        break;
                    }
                }
                if (shmid<0) throw new java.io.IOException("The game display could not start.");
                Thread drain=new Thread(() -> { try (BufferedReader reader=r) { while (reader.readLine()!=null) {} }
                    catch (Exception ignored) {} },"X11-log");
                drain.setDaemon(true); drain.start();
            }
        } catch (Exception ex) { error(ex.toString()); }
    }
    private void attach(SurfaceHolder holder) {
        if (destroyed || !holder.getSurface().isValid()) return;
        String result=DisplayBridge.start(holder.getSurface(),ROOT+"/tmp/.fxshm/sock",shmid,60,ROOT+"/tmp/fxpresent.sock");
        android.util.Log.i("God of War III",result);
        if (!result.startsWith("bridge running:")) { error(result); return; }
        XInput.connect(0);
        if (!displayOnly && game==null) worker.execute(() -> startGame());
        pollFrames();
        if (!imePolling) { imePolling=true; pollIme(); }
    }
    // ---- Game folder: the extracted retail game in shared storage ----
    /** Known retail folder names; the selected folder is still validated by eboot.bin. */
    private static final String[] SERIALS={"CUSA01715","CUSA01740","CUSA00900","CUSA00207","CUSA00208","CUSA00299",
        "CUSA01363","CUSA03179","CUSA03014","CUSA03023"};
    private static boolean isGame(File dir) { return dir!=null && new File(dir,"eboot.bin").isFile(); }
    private boolean hasGame() {
        // Match GameFolderManager: the selected real path is the source of truth.
        // Android 11+ all-files access and app-owned PKG destinations do not need
        // READ_EXTERNAL_STORAGE. Requiring that obsolete permission here rejected
        // folders the launcher had already validated, before starting the runtime.
        return gameDir!=null && isGame(new File(gameDir));
    }
    /** Explains, asks for storage access when needed, then opens the folder picker. */
    private void askGameFolder(boolean change) {
        if (Build.VERSION.SDK_INT>=23 && checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE)
                !=android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.READ_EXTERNAL_STORAGE,
                android.Manifest.permission.WRITE_EXTERNAL_STORAGE},REQUEST_STORAGE);
            return;
        }
        status.setText(UiText.get(this, change ? "Choose the God of War III game folder." :
            "Choose your God of War III game folder (e.g. CUSA01740, the folder with eboot.bin)."));
        status.setVisibility(View.VISIBLE);
        new AlertDialog.Builder(this).setTitle(UiText.get(this, "God of War III game folder"))
            .setMessage(UiText.get(this, "Select the extracted game folder (e.g. CUSA01740 or CUSA00900, which contains eboot.bin) or the folder "
                +"that holds it, in your phone's storage."+(gameDir!=null ? "\n\nCurrent: "+gameDir : "")))
            .setPositiveButton(UiText.get(this, "Choose folder"),(d,w) -> {
                Intent pick=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
                try { startActivityForResult(pick,REQUEST_FOLDER); }
                catch (Exception ex) { error("No folder picker: "+ex); }
            })
            .setNegativeButton(UiText.get(this, change ? "Cancel" : "Quit"),(d,w) -> { if (!change) finish(); })
            .setCancelable(change).show();
    }
    @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] results) {
        super.onRequestPermissionsResult(code,permissions,results);
        if (code!=REQUEST_STORAGE) return;
        if (results.length>0 && results[0]==android.content.pm.PackageManager.PERMISSION_GRANTED) {
            if (hasGame()) startPending(); else askGameFolder(false);
        } else error("God of War III needs storage access to read the game folder.");
    }
    @Override protected void onActivityResult(int code,int result,Intent data) {
        super.onActivityResult(code,result,data);
        if (code!=REQUEST_FOLDER) return;
        if (result!=RESULT_OK || data==null || data.getData()==null) { if (!hasGame()) askGameFolder(false); return; }
        File dir=folderOf(data.getData());
        if (dir!=null && !isGame(dir))
            for (String serial : SERIALS) if (isGame(new File(dir,serial))) { dir=new File(dir,serial); break; }
        if (!isGame(dir)) {
            new AlertDialog.Builder(this).setTitle(UiText.get(this, "Not a God of War III folder"))
                .setMessage(UiText.get(this, (dir==null ? "That location" : dir.getPath())+" has no eboot.bin."))
                .setPositiveButton(UiText.get(this, "Choose again"),(d,w) -> askGameFolder(gameDir!=null)).show();
            return;
        }
        boolean changed=gameDir!=null && !gameDir.equals(dir.getPath());
        gameDir=dir.getPath();
        getSharedPreferences("gow3",MODE_PRIVATE).edit().putString("game_dir",gameDir).apply();
        status.setText(UiText.get(this, "Starting God of War III…"));
        if (changed && game!=null) restartGame(); else startPending();
    }
    /** A storage folder of the picker (tree document "primary:Path" or "XXXX-XXXX:Path") as a path. */
    private static File folderOf(android.net.Uri tree) {
        try {
            String id=android.provider.DocumentsContract.getTreeDocumentId(tree);
            int colon=id.indexOf(':');
            String volume=colon<0 ? id : id.substring(0,colon), path=colon<0 ? "" : id.substring(colon+1);
            File base="primary".equalsIgnoreCase(volume) ? android.os.Environment.getExternalStorageDirectory()
                                                         : new File("/storage/"+volume);
            return path.isEmpty() ? base : new File(base,path);
        } catch (Exception ex) { return null; }
    }
    private void startPending() {
        SurfaceHolder h=pendingHolder!=null ? pendingHolder : surface.getHolder();
        pendingHolder=null;
        startRuntime(h);
    }

    private void pollFrames() {
        if (destroyed) return;
        if (!hadError && (bionicRuntime() ? Gow3Present.framesIfLoaded() : DisplayBridge.directFrames())>0) status.setVisibility(View.GONE);
        main.postDelayed(this::pollFrames,1000);
    }

    /** The game's text dialog (the character name, GOW3_IME_FILE in run-gow3.sh): shown here with the
     *  touch keyboard. The request holds the maximum length, the title and the current text. */
    private void pollIme() {
        if (destroyed) return;
        File request=new File(BASE,"ime.request");
        if (!imeOpen && request.isFile()) {
            try (BufferedReader r=new BufferedReader(new InputStreamReader(new java.io.FileInputStream(request),"UTF-8"))) {
                int max=Integer.parseInt(r.readLine().trim());
                String title=r.readLine(), initial=r.readLine();
                request.delete();
                showIme(Math.max(1,max),title==null ? "" : title,initial==null ? "" : initial);
            } catch (Exception ex) { android.util.Log.e("God of War III","text request: "+ex); request.delete(); }
        }
        main.postDelayed(this::pollIme,250);
    }
    private void showIme(int max,String title,String initial) {
        imeOpen=true; imeAnswered.set(false); pad.reset(); closeDrawer();
        EditText field=new EditText(this);
        field.setSingleLine(true); field.setText(initial); field.setSelection(field.getText().length());
        field.setFilters(new InputFilter[]{new InputFilter.LengthFilter(max)});
        field.setImeOptions(EditorInfo.IME_ACTION_DONE | EditorInfo.IME_FLAG_NO_EXTRACT_UI);
        FrameLayout box=new FrameLayout(this); box.setPadding(dp(20),dp(8),dp(20),0); box.addView(field);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(UiText.get(this, title.isEmpty() ? "Enter text" : title))
            .setView(box)
            .setPositiveButton(UiText.get(this, "OK"),(d,w) -> answerIme(true,field.getText().toString()))
            .setNegativeButton(UiText.get(this, "Cancel"),(d,w) -> answerIme(false,""))
            .setOnCancelListener(d -> answerIme(false,"")).create();
        field.setOnEditorActionListener((v,action,event) -> {
            if (action!=EditorInfo.IME_ACTION_DONE) return false;
            dialog.dismiss(); answerIme(true,field.getText().toString()); return true;
        });
        dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE);
        dialog.setOnDismissListener(d -> { imeOpen=false; imeField=null; imeDialog=null; immersive(); surface.requestFocus(); });
        dialog.setOnKeyListener((d,code,event) -> imeGamepad(event));
        imeField=field; imeDialog=dialog;
        dialog.show(); field.requestFocus();
    }
    /** Consume both edges so accepting a name cannot also press Cross in the game. */
    private boolean imeGamepad(KeyEvent e) {
        if (!imeOpen) return false;
        int code=e.getKeyCode(), scan=e.getScanCode();
        boolean cross=code==KeyEvent.KEYCODE_BUTTON_A || scan==304;
        boolean circle=code==KeyEvent.KEYCODE_BUTTON_B || scan==305;
        if (!cross && !circle) return false;
        if (e.getAction()==KeyEvent.ACTION_UP) {
            EditText field=imeField;
            AlertDialog dialog=imeDialog;
            answerIme(cross, cross && field!=null ? field.getText().toString() : "");
            if (dialog!=null) dialog.dismiss();
        }
        return true;
    }
    private void answerIme(boolean ok,String value) {
        if (!imeAnswered.compareAndSet(false,true)) return;
        File temporary=new File(BASE,"ime.request.result.tmp"), result=new File(BASE,"ime.request.result");
        try (java.io.Writer w=new java.io.OutputStreamWriter(new java.io.FileOutputStream(temporary),"UTF-8")) {
            w.write((ok ? "ok" : "cancel")+"\n"+value.replace('\n',' ')+"\n");
        } catch (Exception ex) { android.util.Log.e("God of War III","text answer: "+ex); return; }
        if (!temporary.renameTo(result)) android.util.Log.e("God of War III","text answer: rename failed");
    }
    /** The last value of a gow3.ini setting (as run-gow3.sh reads it), or null. */
    private String setting(String key) {
        String value=null;
        try (BufferedReader r=new BufferedReader(new java.io.FileReader(new File(BASE,"gow3.ini")))) {
            for (String line; (line=r.readLine())!=null;)
                if (line.startsWith(key+"=")) value=line.substring(key.length()+1).trim();
        } catch (Exception ignored) {}
        return value;
    }
    private void startGame() {
        if (destroyed) return;
        hadError=false;
        new File(BASE,"ime.request").delete(); new File(BASE,"ime.request.result").delete();
        try {
            Process launched=bionicRuntime() ? process("/system/bin/sh",BASE+"/run-bionic.sh","game")
                : process(ROOT+"/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1",
                    ROOT+"/bin/sh",BASE+"/run-gow3.sh","game"); game=launched;
            Thread log=new Thread(() -> {
                try (BufferedReader r=new BufferedReader(new InputStreamReader(launched.getInputStream()));
                     PrintWriter out=new PrintWriter(new File(BASE,"logs/android-game.log"))) {
                    String line; while ((line=r.readLine())!=null) { out.println(line); out.flush(); }
                    int code=launched.waitFor();
                    if (game==launched) {
                        game=null;
                        // run-gow3.sh exits 4 when Vulkan/Turnip cannot initialize: the driver
                        // failure must not be reported as validated texture integrity.
                        if (code==4) error("Graphics initialization failed (Vulkan/Turnip). See logs/android-game.log.");
                        else error("Game stopped ("+code+"). Open the menu to restart.");
                    }
                } catch (Exception ex) {
                    // A restart (settings, cheats) kills this process on purpose: its reader is
                    // interrupted then, after the next game started. Only the current game's errors show.
                    if (!destroyed && game==launched) error(ex.toString());
                }
            },"God of War III-log"); log.setDaemon(true); log.start();
        } catch (Exception ex) { error(ex.toString()); }
    }
    private void error(String message) {
        hadError=true;
        android.util.Log.e("God of War III",message);
        main.post(() -> { if (!destroyed) { status.setText(UiText.get(this, message)); status.setVisibility(View.VISIBLE); } });
    }
    private void stopGame() {
        Process p=game; game=null;
        if (p!=null) { p.destroyForcibly(); try { p.waitFor(); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } }
    }
    @Override protected void onDestroy() {
        destroyed=true; if (perfHud!=null) perfHud.release();
        pad.reset(); audio.stop(); main.removeCallbacksAndMessages(null);
        if (bionicRuntime()) Gow3Present.stop(); else DisplayBridge.stop(); stopGame(); if (xvfb!=null) xvfb.destroyForcibly();
        worker.shutdownNow(); super.onDestroy();
    }
}
