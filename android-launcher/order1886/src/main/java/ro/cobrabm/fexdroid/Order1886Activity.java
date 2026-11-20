package ro.cobrabm.fexdroid;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ActivityInfo;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.ArrayAdapter;
import android.widget.TextView;
import android.widget.Toast;
import android.widget.CheckBox;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Standalone Android launcher for The Order: 1886 — no GoW3 UI or runtime dependencies. */
public final class Order1886Activity extends Activity {
    private static final int INK=0xff101319, PANEL=0xff1b2029, GOLD=0xffd2b778,
                             WHITE=0xffe9e9eb, MUTED=0xffa6abb3, EDGE=0xff39404b;
    private static final int REQ_PKG=111, REQ_UPDATE=112, REQ_FOLDER=113,
                             REQ_DRIVER=114, REQ_BOOT=115, REQ_EXPORT=116,
                             REQ_STORAGE=117, REQ_SAVE_EXPORT=118, REQ_SAVE_IMPORT=119;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final AtomicBoolean working=new AtomicBoolean();
    private File base,gameDir,logFile,manualBoot;
    private Order1886PadBridge pad;
    private Order1886AudioBridge audio;
    private Order1886Content content;
    private Order1886SaveManager saveManager;
    private Order1886Preparation preparer;
    private Order1886DriverStore drivers;
    private FrameLayout screen, gameFrame;
    private Order1886TouchOverlay touchLayer;
    private LinearLayout mainUI,body,tabs;
    private SurfaceView surface;
    private TextView status,gameHud,gameTitle;
    private volatile Process game;
    private volatile boolean stopped=true;
    private boolean presentStarted, gameOpen;
    private int page=0, pendingStorage=0;
    private String statusText="Pronto para configurar o jogo.";
    private AlertDialog gameMenuDialog;
    private float swipeX, swipeY;
    private boolean swipeCandidate, swipeConsumed, editingControls;
    private long previousFrameCount, previousFpsMs;
    private float fpsSmoothed=-1f;
    private final Runnable fpsPoll=new Runnable(){
        @Override public void run(){
            if(!gameOpen)return;
            try {
                long count=Order1886Present.framesIfLoaded();
                long now=android.os.SystemClock.elapsedRealtime();
                long elapsed=now-previousFpsMs;
                if(previousFpsMs>0 && elapsed>=250 && count>=previousFrameCount){
                    float fps=1000f*(count-previousFrameCount)/elapsed;
                    fpsSmoothed=fpsSmoothed<0f?fps:(0.5f*fpsSmoothed+0.5f*fps);
                    if(gameHud!=null)gameHud.setText(String.format(Locale.US,"%.1f FPS",fpsSmoothed));
                }
                previousFrameCount=count;
                previousFpsMs=now;
            }catch(Throwable ignored){}
            main.postDelayed(this,500);
        }
    };

    private android.content.SharedPreferences prefs(){return getSharedPreferences("order1886",MODE_PRIVATE);}
    private String tr(String text){return Order1886UiText.translate(this,text);}
    private String[] translated(String[] texts){String[] v=new String[texts.length];for(int i=0;i<texts.length;i++)v[i]=tr(texts[i]);return v;}
    // The Order: v0.1.8 dependency-aware SRT flattening changes shader metadata; rebuild derived cache.
    // Touch only derived CUSA shader data, never game PKGs, saves or user settings.
    private static void deleteShaderCacheTree(File root,File file) throws IOException {
        File canonicalRoot=root.getCanonicalFile(),canonicalFile=file.getCanonicalFile();
        if(!canonicalFile.toPath().startsWith(canonicalRoot.toPath()) ||
           java.nio.file.Files.isSymbolicLink(file.toPath()))
            throw new IOException("Unsafe shader cache path");
        File[] children=file.listFiles();
        if(children!=null)for(File child:children)deleteShaderCacheTree(root,child);
        if(!file.delete()&&file.exists())throw new IOException("Cannot delete cached shader "+file);
    }
    private void invalidateOldSrtShaders() throws IOException {
        if(prefs().getBoolean("srtDepsAndTextureBindingV018",false))return;
        File root=new File(base,".local/share/shadPS4/cache");
        File[] folders=root.listFiles();
        if(folders!=null)for(File f:folders) {
            if(f.isDirectory()&&f.getName().matches("CUSA[0-9]{5}"))
                deleteShaderCacheTree(root,f);
        }
        if(!prefs().edit().putBoolean("srtDepsAndTextureBindingV018",true).commit())
            throw new IOException("Could not persist shader cache version");
    }
    // PS4 display fit/fill is separate from the Android immersive-bars policy.
    private void setGameImmersive(boolean enabled) {
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(!enabled);
            WindowInsetsController controller=getWindow().getInsetsController();
            if (controller!=null) {
                if (enabled) {
                    controller.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                    controller.hide(WindowInsets.Type.statusBars()|WindowInsets.Type.navigationBars());
                } else controller.show(WindowInsets.Type.statusBars()|WindowInsets.Type.navigationBars());
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(enabled
                ? View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_FULLSCREEN|
                  View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|
                  View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                : 0);
        }
    }
    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (focused && gameOpen) main.post(()->{if(gameOpen)setGameImmersive(true);});
    }
    private int dp(float d){return (int)(d*getResources().getDisplayMetrics().density+.5f);}
    private GradientDrawable shape(int color,int stroke,int radius){
        GradientDrawable d=new GradientDrawable();
        d.setColor(color); d.setCornerRadius(dp(radius));
        if(stroke!=0)d.setStroke(dp(1),stroke);
        return d;
    }
    private TextView label(String text,int sp,int color,boolean bold){
        TextView v=new TextView(this);v.setText(tr(text));v.setTextColor(color);
        v.setTextSize(sp);if(bold)v.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        v.setIncludeFontPadding(false);return v;
    }
    private Button button(String name, boolean accent,View.OnClickListener listener){
        Button b=new Button(this);
        b.setAllCaps(false);b.setText(tr(name));b.setTextSize(13);
        b.setTextColor(accent?INK:WHITE);
        b.setBackground(shape(accent?GOLD:0xff272e38,accent?0:EDGE,9));
        b.setPadding(dp(10),dp(3),dp(10),dp(3));
        b.setOnClickListener(listener);return b;
    }
    private LinearLayout column(){LinearLayout v=new LinearLayout(this);v.setOrientation(LinearLayout.VERTICAL);return v;}
    private LinearLayout horizontal(){LinearLayout v=new LinearLayout(this);v.setOrientation(LinearLayout.HORIZONTAL);v.setGravity(Gravity.CENTER_VERTICAL);return v;}
    private void line(LinearLayout parent,String title,String secondary){
        TextView h=label(title,14,WHITE,true);
        parent.addView(h);
        if(secondary!=null&&!secondary.isEmpty()){
            TextView sub=label(secondary,12,MUTED,false);
            sub.setPadding(0,dp(5),0,0);
            parent.addView(sub);
        }
    }
    private void gap(LinearLayout parent,int px){View g=new View(this);parent.addView(g,new LinearLayout.LayoutParams(1,dp(px)));}
    private LinearLayout card(LinearLayout parent,String caption){
        LinearLayout c=column();c.setPadding(dp(15),dp(12),dp(15),dp(14));
        c.setBackground(shape(PANEL,EDGE,12));
        LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(-1,-2);cp.bottomMargin=dp(12);
        parent.addView(c,cp);
        if(caption!=null){TextView t=label(tr(caption).toUpperCase(Locale.ROOT),12,GOLD,true);c.addView(t);gap(c,9);}
        return c;
    }
    private void actions(LinearLayout target,Button... buttons){
        LinearLayout row=horizontal();
        row.setGravity(Gravity.LEFT);
        row.setPadding(0,dp(7),0,0);
        for(Button b:buttons){
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(46),1f);
            lp.rightMargin=dp(6);
            row.addView(b,lp);
        }
        target.addView(row);
    }
    private void show(String message){
        message=tr(message);
        statusText=message;
        final String translatedMessage=message;
        main.post(() -> {
            if(status!=null)status.setText(translatedMessage);
            if(!gameOpen&&page==0)updateHomeHeader();
        });
    }
    private void busy(String text){show(text);}
    @Override public void onCreate(Bundle bundle){
        super.onCreate(bundle);
        getWindow().setStatusBarColor(INK);getWindow().setNavigationBarColor(Color.BLACK);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
        base=new File(getFilesDir(),"order1886");base.mkdirs();
        manualBoot=new File(base,"manual-boot-linked.bin");
        logFile=new File(base,"last-runtime.log");
        content=new Order1886Content(this);
        saveManager=new Order1886SaveManager(this,base);
        preparer=new Order1886Preparation(this,new File(base,"user"));
        drivers=new Order1886DriverStore(this);
        pad=new Order1886PadBridge(new File(base,"pad.state"));
        pad.setRightStickZRZ(prefs().getBoolean("rightStickZRZ",false));
        audio=new Order1886AudioBridge(new File(base,"audio.fifo"));
        String path=prefs().getString("gameDir",null);
        if(path!=null){File f=new File(path);if(isGame(f))gameDir=f;}
        build();
        render();
        show("Selecione uma pasta extraída ou instale o PKG do jogo. "+
            (content.available()?"Extrator ARM64 disponível.":"Extrator ARM64 ausente."));
    }
    private void build(){
        screen=new FrameLayout(this);screen.setBackgroundColor(INK);
        mainUI=column();
        mainUI.setBackgroundColor(INK);
        FrameLayout.LayoutParams fill=new FrameLayout.LayoutParams(-1,-1);
        screen.addView(mainUI,fill);
        LinearLayout titleRow=horizontal();
        titleRow.setPadding(dp(24),dp(16),dp(24),dp(12));
        TextView emblem=label("THE ORDER 1886",23,WHITE,true);
        titleRow.addView(emblem);
        TextView tag=label("   DAEDALUS • BIONIC",11,GOLD,true);
        titleRow.addView(tag);
        mainUI.addView(titleRow);
        tabs=horizontal();tabs.setPadding(dp(16),0,dp(16),dp(6));
        mainUI.addView(tabs);
        ScrollView scroll=new ScrollView(this);
        scroll.setFillViewport(false);scroll.setClipToPadding(false);
        scroll.setPadding(dp(18),dp(5),dp(18),dp(6));
        body=column();body.setPadding(0,0,0,dp(14));
        scroll.addView(body);
        mainUI.addView(scroll,new LinearLayout.LayoutParams(-1,0,1f));
        status=label(statusText,12,GOLD,false);
        status.setBackgroundColor(0xff171b22);status.setPadding(dp(18),dp(9),dp(18),dp(9));
        status.setMaxLines(2);
        mainUI.addView(status,new LinearLayout.LayoutParams(-1,-2));

        gameFrame=new FrameLayout(this);gameFrame.setBackgroundColor(Color.BLACK);
        screen.addView(gameFrame,fill);gameFrame.setVisibility(View.GONE);
        surface=new SurfaceView(this);
        gameFrame.addView(surface,new FrameLayout.LayoutParams(-1,-1));
        touchLayer=new Order1886TouchOverlay(this,pad);
        gameFrame.addView(touchLayer,new FrameLayout.LayoutParams(-1,-1));
        gameHud=label("— FPS",14,GOLD,true);
        gameFrame.addView(gameHud,new FrameLayout.LayoutParams(-2,-2,Gravity.TOP|Gravity.RIGHT));
        applyHudStyle();
        // Game menu is driven by dispatchTouchEvent and Android's system Back gesture.
        // Do not overlay a permanent invisible button on the PlayStation controls.
        setContentView(screen);
    }

    private void applyHudStyle(){
        if(gameHud==null)return;
        int size=prefs().getInt("hudSize",1);
        gameHud.setTextSize(size==0?12:size==2?18:15);
        gameHud.setTextColor(GOLD);
        gameHud.setBackground(shape(0xb5111720,0x775f5c51,8));
        gameHud.setPadding(dp(9),dp(5),dp(9),dp(5));
        int position=prefs().getInt("hudPosition",2);
        FrameLayout.LayoutParams params=(FrameLayout.LayoutParams)gameHud.getLayoutParams();
        params.gravity=Gravity.TOP|(position==0?Gravity.LEFT:
            position==1?Gravity.CENTER_HORIZONTAL:Gravity.RIGHT);
        params.leftMargin=position==0?dp(12):0;
        params.rightMargin=position==2?dp(12):0;
        params.topMargin=dp(10);
        gameHud.setLayoutParams(params);
        gameHud.setVisibility(prefs().getBoolean("hudVisible",true)?View.VISIBLE:View.GONE);
    }
    private void showGameMenu(){
        if(!gameOpen || gameMenuDialog!=null && gameMenuDialog.isShowing())return;
        if(touchLayer!=null)touchLayer.release();
        final boolean controls=prefs().getBoolean("onscreen",true);
        final boolean fill=prefs().getBoolean("fullscreen",false);
        final boolean hud=prefs().getBoolean("hudVisible",true);
        AlertDialog dialog=new AlertDialog.Builder(this)
            .setTitle("THE ORDER 1886 / DAEDALUS")
            .setItems(translated(new String[]{
                "Retomar jogo",
                controls?"Ocultar controles PlayStation":"Mostrar controles PlayStation",
                "Editar posição dos controles",
                "Restaurar layout clássico",
                fill?"Enquadramento: Ajustar (Fit)":"Enquadramento: Preencher (Fill)",
                hud?"Ocultar HUD de FPS":"Mostrar HUD de FPS",
                "Exportar log",
                "Voltar ao launcher / Sair do jogo"
            }),(d,index)->{
                switch(index){
                    case 1:
                        prefs().edit().putBoolean("onscreen",!controls).apply();
                        setupTouchControls();
                        break;
                    case 2:
                        prefs().edit().putBoolean("onscreen",true).apply();
                        setupTouchControls();
                        editingControls=true;
                        touchLayer.edit(()->{editingControls=false;setupTouchControls();});
                        break;
                    case 3:
                        touchLayer.resetLayout();
                        setupTouchControls();
                        break;
                    case 4:
                        prefs().edit().putBoolean("fullscreen",!fill).apply();
                        if(presentStarted)Order1886Present.setFullscreen(!fill);
                        break;
                    case 5:
                        prefs().edit().putBoolean("hudVisible",!hud).apply();
                        applyHudStyle();
                        break;
                    case 6:
                        exportLog();
                        break;
                    case 7:
                        stopGame();
                        break;
                    default:break;
                }
            }).create();
        gameMenuDialog=dialog;
        dialog.setOnDismissListener(d->{
            gameMenuDialog=null;
            if(gameOpen)setGameImmersive(true);
        });
        dialog.show();
        android.view.Window window=dialog.getWindow();
        if(window!=null){
            window.setBackgroundDrawable(shape(PANEL,EDGE,12));
            window.setGravity(Gravity.RIGHT|Gravity.TOP);
            window.setLayout(Math.min(dp(380),
                (int)(getResources().getDisplayMetrics().widthPixels*.82f)),-1);
            window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);
            WindowManager.LayoutParams params=window.getAttributes();
            params.dimAmount=.55f;
            window.setAttributes(params);
        }
    }
    private void updateHomeHeader(){ /* Status updates stay in the fixed footer; do not rebuild during a job. */ }
    private void render(){
        if(gameOpen)return;
        tabs.removeAllViews();
        String[] items={"Início","Gráficos","Drivers","Ferramentas"};
        for(int i=0;i<items.length;i++){
            final int at=i;
            Button b=button(items[i],i==page,v->{page=at;render();});
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(38),1f);
            lp.rightMargin=dp(6);tabs.addView(b,lp);
        }
        body.removeAllViews();
        switch(page){
            case 0:renderHome();break;
            case 1:renderGraphics();break;
            case 2:renderDrivers();break;
            default:renderTools();
        }
    }
    private boolean isGame(File dir){
        return dir!=null && new File(dir,"eboot.bin").isFile() &&
              new File(dir,"sce_sys/param.sfo").isFile();
    }
    private File currentImage(){
        // Avoid booting a stale preparation when game folder/eboot/settings change.
        String recorded=prefs().getString("preparedSignature","");
        if(preparer.prepared()&&prepSignature().equals(recorded))return preparer.image();
        return "manual".equals(recorded)&&manualBoot.isFile()?manualBoot:null;
    }
    private String disabledEffects(){
        ArrayList<String> effects=new ArrayList<>();
        if(prefs().getBoolean("disableMotionBlur",false))effects.add("motion_blur");
        if(prefs().getBoolean("disableDepthOfField",false))effects.add("depth_of_field");
        if(prefs().getBoolean("disableFilmGrain",false))effects.add("film_grain");
        if(prefs().getBoolean("disableChromatic",false))effects.add("chromatic_aberration");
        return String.join(",",effects);
    }
    private String prepSignature(){
        return prefs().getInt("fps",30)+":"+
            prefs().getString("aspect","original")+":"+
            prefs().getInt("width",1920)+":"+disabledEffects()+":"+prefs().getString("readback","relaxed")+":"+prefs().getInt("language",1)+":"+
            (gameDir==null?"none":gameDir.getAbsolutePath())+":"+
            (gameDir==null?0:new File(gameDir,"eboot.bin").length())+":"+
            (gameDir==null?0:new File(gameDir,"eboot.bin").lastModified());
    }
    private void renderHome(){
        LinearLayout headline=card(body,"Biblioteca de jogos");
        String name=gameDir==null?"Nenhum jogo instalado ou selecionado":"The Order: 1886 • "+gameDir.getName();
        line(headline,name,gameDir==null?
            "Instale um PKG ou selecione a pasta que já contém eboot.bin e sce_sys.":
            gameDir.getAbsolutePath());
        TextView prepared=label(currentImage()==null?"Imagem de boot: precisa preparar":
            "Imagem de boot: "+(preparer.prepared()?"preparada no Android":"importada"),12,
            currentImage()!=null?GOLD:MUTED,true);
        prepared.setPadding(0,dp(9),0,0);headline.addView(prepared);
        actions(headline,
            button("Instalar PKG",true,v->pickPkg(false)),
            button("Pasta existente",false,v->pickFolder()));
        actions(headline,button("Instalar atualização",false,v->pickPkg(true)),
                         button("Preparar jogo",false,v->prepareGame()));
        LinearLayout launch=card(body,"Executar no dispositivo");
        line(launch,"Bionic + FEX + Vulkan",
            "GPU: "+drivers.description()+"   •   "+prefs().getInt("fps",30)+" FPS configurado"+
            "   •   "+(prefs().getBoolean("onscreen",true)?"Controles na tela":"Controle físico"));
        actions(launch,button("▶  INICIAR JOGO",true,v->startGame()),
            button("Diagnóstico",false,v->diagnose()));
        LinearLayout note=card(body,"Estado do port");
        line(note,"Versão experimental • sem garantia de gameplay",
            "A primeira execução verifica importações, renderização Vulkan e inicialização PS4. "+
            "Erros são registrados em Ferramentas → Exportar log. "+
            "Não há arquivos do jogo incluídos.");
    }
    private Spinner selectSpinner(LinearLayout parent,String title,String[] items,int selected,
                                   java.util.function.Consumer<Integer> changed){
        LinearLayout box=horizontal();
        TextView t=label(title,14,WHITE,false);
        box.addView(t,new LinearLayout.LayoutParams(0,-2,1f));
        Spinner spinner=new Spinner(this);
        ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,translated(items));
        spinner.setAdapter(adapter);spinner.setSelection(selected);
        spinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){
            private boolean initialized;
            @Override public void onItemSelected(android.widget.AdapterView<?> p,View v,int i,long id){
                if(!initialized){initialized=true;return;}
                changed.accept(i);
            }
            @Override public void onNothingSelected(android.widget.AdapterView<?> p){}
        });
        box.addView(spinner,new LinearLayout.LayoutParams(dp(180),dp(49)));
        parent.addView(box);return spinner;
    }
    private void selectionChange(){
        show("Configuração salva. Prepare novamente o jogo se mudou FPS, proporção ou resolução.");
    }
    private void toggle(LinearLayout card,String label,String key,boolean def){
        CheckBox box=new CheckBox(this);box.setText(tr(label));box.setTextColor(WHITE);
        box.setChecked(prefs().getBoolean(key,def));
        box.setOnCheckedChangeListener((b,checked)->{
            prefs().edit().putBoolean(key,checked).apply();selectionChange();
        });
        card.addView(box);
    }
    private void renderGraphics(){
        LinearLayout c=card(body,"Configurações reais de vídeo");
        String uiLang=prefs().getString("appLanguage","auto");
        selectSpinner(c,"Idioma do aplicativo",new String[]{"Automático (sistema)","Português (Brasil)","English"},
            "pt".equals(uiLang)?1:"en".equals(uiLang)?2:0,
            n->{prefs().edit().putString("appLanguage",n==1?"pt":n==2?"en":"auto").apply();render();});
        String[] fps={"30 FPS (padrão)","60 FPS (experimental)"};
        selectSpinner(c,"Taxa do jogo",fps,prefs().getInt("fps",30)==60?1:0,
            n->{prefs().edit().putInt("fps",n==0?30:60).apply();selectionChange();});
        String[] widths={"1920 (nativo)","1600 (900p)","1280 (720p)"};
        int width=prefs().getInt("width",1920);
        selectSpinner(c,"Largura de renderização",widths,width==1280?2:width==1600?1:0,
            n->{prefs().edit().putInt("width",n==0?1920:n==1?1600:1280).apply();selectionChange();});
        selectSpinner(c,"Enquadramento",new String[]{"Cinematográfico original","16:9 experimental"},
            "16:9".equals(prefs().getString("aspect","original"))?1:0,
            n->{prefs().edit().putString("aspect",n==0?"original":"16:9").apply();selectionChange();});
        selectSpinner(c,"Readback",new String[]{"Relaxed","Selective","Precise"},
            "precise".equals(prefs().getString("readback","relaxed"))?2:
            "selective".equals(prefs().getString("readback","relaxed"))?1:0,
            n->{prefs().edit().putString("readback",
                n==2?"precise":n==1?"selective":"relaxed").apply();selectionChange();});
        selectSpinner(c,"Filtro de apresentação",new String[]{"FSR 1 espacial","Linear (sem FSR)"},
            "linear".equals(prefs().getString("filter","fsr1"))?1:0,
            n->{prefs().edit().putString("filter",n==0?"fsr1":"linear").apply();selectionChange();});
        selectSpinner(c,"Sharpening RCAS",new String[]{"Desativado","25%","50%","75%","100%"},
            Math.max(0,Math.min(4,prefs().getInt("sharpness",0)/25)),
            n->{prefs().edit().putInt("sharpness",n*25).apply();selectionChange();});
        selectSpinner(c,"Anisotropia",new String[]{"1x","2x","4x","8x","16x"},
            Integer.numberOfTrailingZeros(prefs().getInt("anisotropy",1)),
            n->{prefs().edit().putInt("anisotropy",1<<n).apply();selectionChange();});
        selectSpinner(c,"Frames adiantados",new String[]{"0 (sem limite)","1 (padrão)","2"},
            prefs().getInt("framesQueued",1),
            n->{prefs().edit().putInt("framesQueued",n).apply();selectionChange();});
        selectSpinner(c,"Idioma do jogo",new String[]{"日本語","English (United States)","Français (France)","Español (España)","Deutsch","Italiano","Nederlands","Português (Portugal)","Русский","한국어","繁體中文","简体中文","Suomi","Svenska","Dansk","Norsk","Polski","Português (Brasil)","English (United Kingdom)","Türkçe","Español (Latinoamérica)","العربية","Français (Canada)","Čeština","Magyar","Ελληνικά","Română","ไทย","Tiếng Việt","Bahasa Indonesia"},
            Math.max(0,Math.min(29,prefs().getInt("language",1))),
            n->{prefs().edit().putInt("language",n).apply();selectionChange();});
        toggle(c,"VSync", "vsync",false);
        toggle(c,"Shaders assíncronos", "asyncShaders",true);
        toggle(c,"Perfil de desempenho do motor (-msaa 1 / -disablecloth)",
               "enginePerf",true);
        line(c,"Redução de GPU compatível",
            "Mantém o desenho de sombras para evitar o crash da versão 0.1.21; "+
            "a união de passes Vulkan permanece disponível.");
        toggle(c,"Reduzir GPU: juntar passes após a limpeza de imagem",
               "gpuTileMerge",true);
        toggle(c,"Reduzir GPU: limpar attachments sem fechar passe (Adreno)",
               "gpuInlineClear",true);
        toggle(c,"Medidores de tempo GPU/CPU nos logs (amostragem)",
               "gpuMeters",true);
        line(c,"Medição de gargalos",
            "O Vulkan mede um frame a cada 90: sombras, G-buffer, cena, pós, "+
            "compute e cópias. Resultados de GPU e CPU são agregados no log "+
            "sem criar registros por draw nem esperar a GPU responder.");
        line(c,"Passes Vulkan móveis",
            "Quando um render target acabou de ser limpo, o próximo draw no mesmo "+
            "alvo não precisa encerrar o passe e recarregar os tiles; só funde "+
            "se o próximo draw não pedir nova limpeza.");
        line(c,"Motor do jogo: perfil experimental",
            "Usa opções já existentes no eboot 01.02 para reduzir MSAA e simulação de tecido. "+
            "Desative caso apareçam falhas; o ganho de GPU precisa ser testado.");
        toggle(c,"Preencher tela Android (Fill; desativado = Fit)","fullscreen",false);
        CheckBox showTouch=new CheckBox(this);
        showTouch.setText(tr("Controles PlayStation na tela"));showTouch.setTextColor(WHITE);
        showTouch.setChecked(prefs().getBoolean("onscreen",true));
        showTouch.setOnCheckedChangeListener((v,enabled)->{
            prefs().edit().putBoolean("onscreen",enabled).apply();
            setupTouchControls();
        });
        c.addView(showTouch);
        toggle(c,"Analógico direito: usar Z/RZ (controle físico)","rightStickZRZ",false);
        selectSpinner(c,"Tamanho dos controles",new String[]{"Compacto","Clássico","Grande"},
            Math.max(0,Math.min(2,prefs().getInt("controlSize",1))),
            n->{
                prefs().edit().putInt("controlSize",n).apply();
                if(touchLayer!=null)touchLayer.invalidate();
            });
        final int[] alphaLevels={50,65,78,90,100};
        int savedOpacity=prefs().getInt("controlOpacity",78), alphaIndex=2;
        for(int i=0;i<alphaLevels.length;i++)if(savedOpacity==alphaLevels[i])alphaIndex=i;
        selectSpinner(c,"Opacidade dos controles",
            new String[]{"50%","65%","78%","90%","100%"},alphaIndex,
            n->{
                prefs().edit().putInt("controlOpacity",alphaLevels[n]).apply();
                if(touchLayer!=null)touchLayer.setAlpha(alphaLevels[n]/100f);
            });

        selectSpinner(c,"Posição HUD FPS",
            new String[]{"Topo esquerdo","Topo central","Topo direito"},
            Math.max(0,Math.min(2,prefs().getInt("hudPosition",2))),
            n->{prefs().edit().putInt("hudPosition",n).apply();applyHudStyle();});
        selectSpinner(c,"Tamanho HUD FPS",new String[]{"Pequeno","Normal","Grande"},
            Math.max(0,Math.min(2,prefs().getInt("hudSize",1))),
            n->{prefs().edit().putInt("hudSize",n).apply();applyHudStyle();});
        CheckBox showHud=new CheckBox(this);
        showHud.setText(tr("Mostrar HUD FPS"));showHud.setTextColor(WHITE);
        showHud.setChecked(prefs().getBoolean("hudVisible",true));
        showHud.setOnCheckedChangeListener((b,enabled)->{
            prefs().edit().putBoolean("hudVisible",enabled).apply();applyHudStyle();
        });
        c.addView(showHud);
        toggle(c,"Aquecimento de shaders em segundo plano (experimental)","warmup",false);
        actions(c,button("Aplicar e preparar jogo",true,v->prepareGame()));
        LinearLayout patches=card(body,"Patches gráficos 01.02");
        line(patches,"Validados no código da edição enviada",
            "O preparador verifica os bytes da versão selecionada e modifica somente a imagem derivada; o eboot.bin nunca é alterado.");
        line(patches,"Patches Vulkan de desempenho",
            "1 e 2 são otimizações internas do renderizador, aplicadas sem alterar a resolução. "+
            "A terceira tenta trocar a conversão do quadro por um blit direto quando os formatos são compatíveis.");
        toggle(patches,"Patch 1: ignorar texturas de luzes inativas","gpuLightGuard",true);
        toggle(patches,"Patch 2: remover limpeza redundante da imagem","gpuPpNoClear",true);
        toggle(patches,"Patch 3: blit BGRA para RGBA sem shader (se compatível)","gpuFastBgraBlit",true);
        toggle(patches,"Desativar motion blur","disableMotionBlur",false);
        toggle(patches,"Desativar profundidade de campo","disableDepthOfField",false);
        toggle(patches,"Desativar film grain","disableFilmGrain",false);
        toggle(patches,"Desativar aberração cromática","disableChromatic",false);
        line(patches,"60 FPS, 16:9 e resolução",
            "Já disponíveis acima. 60 FPS pode causar QTEs travados nos capítulos 6 e 9.");
        LinearLayout note=card(body,"Sobre as configurações");
        line(note,"O jogo aplica patches verificados na imagem preparada.",
            "30/60 FPS, proporção e resolução exigem nova preparação. "+
            "Readback, RCAS, anisotropia e shaders assíncronos são aplicados no runtime. "+
            "FSR 1 é espacial (não FSR 3 temporal); sem DLLs Windows. "+
            "Português BR depende dos arquivos de idioma da edição instalada.");
    }
    private void renderDrivers(){
        LinearLayout c=card(body,"Driver Vulkan");
        line(c,"Driver atual: "+drivers.description(),
            "A Turnip GameHub 26.3 + DD GMEM + PWR_MAX (Experimental) acompanha o APK "+
            "e é usada automaticamente em Adreno. Outras GPUs usam o Vulkan do sistema.");
        actions(c,button("Usar Turnip 26.3 (padrão)",true,v->{
            try{
                drivers.select(Order1886DriverStore.BUNDLED);
                render();
                show("Turnip GameHub 26.3 selecionada. Incluída no APK.");
            }catch(Exception e){show("Driver indisponível: "+e.getMessage());}
        }),button("Usar sistema",false,v->{
            try{drivers.select("system");render();show("Vulkan do sistema selecionado.");}
            catch(Exception e){show(e.getMessage());}
        }));
        actions(c,button("Importar outro driver ZIP",false,v->pickDriver()));
        List<DriverArchive.Installed> list=drivers.installed();
        for(DriverArchive.Installed item:list){
            LinearLayout row=horizontal();row.setPadding(0,dp(8),0,dp(4));
            TextView t=label(item.name,12,WHITE,true);
            row.addView(t,new LinearLayout.LayoutParams(0,-2,1f));
            Button use=button("Selecionar",false,v->{
                try{drivers.select("custom:"+item.id);render();show("Turnip selecionado: "+item.name);}
                catch(Exception e){show("Driver recusado: "+e.getMessage());}
            });
            row.addView(use,new LinearLayout.LayoutParams(dp(112),dp(38)));c.addView(row);
        }
        LinearLayout note=card(body,"Compatibilidade do driver");
        line(note,"O driver é carregado diretamente pelo runtime Vulkan.",
            "GameHub Turnip 26.3 experimental é o padrão no Snapdragon/Adreno. "+
            "Outros drivers podem ser importados; a escolha manual permanece salva. "+
            "Se houver falha de compatibilidade, selecione o Vulkan do sistema.");
    }
    private void renderTools(){
        LinearLayout c=card(body,"Arquivos e diagnóstico");
        line(c,"Runtime ARM64",new File(getApplicationInfo().nativeLibraryDir,
            "liborder1886_probe.so").isFile()?"Bibliotecas nativas presentes":"Bibliotecas nativas ausentes");
        actions(c,button("Importar boot-linked.bin",false,v->selectFile(REQ_BOOT)),
                  button("Exportar log",false,v->exportLog()));
        actions(c,button("Exportar saves ZIP",true,v->exportSaves()),
                  button("Importar saves ZIP",false,v->importSaves()));
        line(c,"Backup de saves","Inclui todos os usuarios, identificadores CUSA, metadados .sce_sys e SaveDataMemory. "
            +"Importe ou exporte com o jogo fechado; arquivos existentes com mesmo nome serao substituidos.");
        actions(c,button("Diagnóstico do runtime",true,v->diagnose()),
                  button("Preparar no celular",false,v->prepareGame()));
        if(gameDir!=null)line(c,"Jogo selecionado",gameDir.getAbsolutePath());
        line(c,"Driver selecionado",drivers.description());
        LinearLayout support=card(body,"Teste e coleta");
        line(support,"Os logs são exportados pelo seletor Android.",
            "Use Diagnóstico para consultar versão e CPU. "+
            "Use Preparar para gerar boot-linked.bin localmente. "+
            "Ao iniciar, o jogo é executado em processo isolado com saída registrada.");
    }
    private void selectFile(int request){
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        startActivityForResult(i,request);
    }
    private void pickPkg(boolean update){
        if(working.get()){show("Já existe uma operação em andamento.");return;}
        if(update && gameDir==null){show("Selecione ou instale primeiro o jogo base.");return;}
        int request=update?REQ_UPDATE:REQ_PKG;
        if(!filePermission()){pendingStorage=request;requestStorage();return;}
        selectFile(request);
    }
    private void pickDriver(){selectFile(REQ_DRIVER);}
    private void pickFolder(){
        if(!filePermission()){pendingStorage=REQ_FOLDER;requestStorage();return;}
        Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(intent,REQ_FOLDER);
    }
    private boolean filePermission(){
        return Build.VERSION.SDK_INT<30||Environment.isExternalStorageManager();
    }
    private void requestStorage(){
        try {
            Intent i=new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:"+getPackageName()));
            startActivityForResult(i,REQ_STORAGE);
        }catch(Exception ex){show("Abra as permissões do aplicativo e permita acesso aos arquivos.");}
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request==REQ_STORAGE){
            if(filePermission()&&pendingStorage!=0){
                int next=pendingStorage;pendingStorage=0;
                if(next==REQ_FOLDER)pickFolder();
                else selectFile(next);
            }else{pendingStorage=0;show("Acesso a arquivos não autorizado.");}
            return;
        }
        if(result!=RESULT_OK||data==null||data.getData()==null)return;
        Uri uri=data.getData();
        switch(request){
            case REQ_FOLDER:
                try {
                    File dir=Order1886Content.localDocument(this,uri,true);
                    if(!isGame(dir))throw new IOException("Pasta sem eboot.bin ou sce_sys/param.sfo.");
                    runTask("Pasta selecionada. Preparação automática iniciada...",()->{
                        gameDir=dir;
                        if(!prefs().edit().putString("gameDir",dir.getAbsolutePath())
                                .remove("preparedSignature").commit())
                            throw new IOException("Falha ao salvar pasta selecionada");
                        doPrepare();
                    });
                    page=0;render();
                }catch(Exception e){show("Pasta inválida: "+e.getMessage());}
                break;
            case REQ_DRIVER:
                runTask("Importando driver ZIP...",()->{
                    DriverArchive.Installed d=drivers.importZip(uri);
                    show("Turnip instalada e selecionada: "+d.name);});
                break;
            case REQ_PKG: case REQ_UPDATE:
                boolean update=request==REQ_UPDATE;
                runTask(update?"Instalando atualização PKG...":"Instalando jogo PKG...",()->{
                    File installed=content.install(uri,update,gameDir,this::show);
                    gameDir=installed;
                    if(!prefs().edit().putString("gameDir",installed.getAbsolutePath())
                            .remove("preparedSignature").commit())
                        throw new IOException("Falha ao salvar PKG instalado");
                    show("PKG instalado. Preparando imagem do jogo...");
                    doPrepare();
                });
                break;
            case REQ_BOOT:
                runTask("Importando boot-linked.bin...",()->{
                    File temporary=new File(base,"manual-boot-linked.bin.tmp");
                    try(InputStream in=getContentResolver().openInputStream(uri);
                        OutputStream out=new FileOutputStream(temporary)){
                        if(in==null)throw new IOException("Documento inacessível");
                        byte[] first=new byte[8];int n=in.read(first);
                        if(n!=8||!"PS4BOOT5".equals(new String(first,StandardCharsets.US_ASCII)))
                            throw new IOException("Assinatura PS4BOOT5 inválida");
                        out.write(first);
                        byte[] buf=new byte[1<<16];while((n=in.read(buf))!=-1)out.write(buf,0,n);
                    }
                    if(manualBoot.isFile()&&!manualBoot.delete())throw new IOException("Não foi possível substituir");
                    if(!temporary.renameTo(manualBoot))throw new IOException("Não foi possível ativar imagem");
                    prefs().edit().putString("preparedSignature","manual").apply();
                    show("Imagem preparada importada: "+(manualBoot.length()/1048576)+" MB");
                });
                break;
            case REQ_SAVE_EXPORT:
                if(gameOpen){show("Feche o jogo antes de exportar saves.");break;}
                runTask("Exportando saves ZIP...",()->{
                    saveManager.exportTo(uri);show("Saves exportados com metadados.");
                });
                break;
            case REQ_SAVE_IMPORT:
                if(gameOpen){show("Feche o jogo antes de importar saves.");break;}
                runTask("Importando saves ZIP...",()->{
                    saveManager.importFrom(uri);show("Saves e metadados importados.");
                });
                break;
            case REQ_EXPORT:
                try(InputStream in=new FileInputStream(logFile);
                    OutputStream out=getContentResolver().openOutputStream(uri)){
                    if(out==null)throw new IOException("Destino indisponível");
                    byte[] buf=new byte[32768];int n;
                    while((n=in.read(buf))!=-1)out.write(buf,0,n);
                    show("Log exportado.");
                }catch(Exception e){show("Falha ao exportar: "+e.getMessage());}
                break;
        }
    }
    private interface Work{void perform() throws Exception;}
    private void runTask(String beginning,Work task){runTask(beginning,task,null);}
    private void runTask(String beginning,Work task,Runnable afterSuccess){
        if(!working.compareAndSet(false,true)){show("Operação anterior ainda ativa.");return;}
        show(beginning);
        new Thread(()->{
            boolean succeeded=false;
            try{task.perform();succeeded=true;}
            catch(Exception e){writeError(e);show("Falha: "+e.getMessage());}
            finally{
                working.set(false);
                final boolean success=succeeded;
                main.post(()->{
                    render();
                    if(success&&afterSuccess!=null)afterSuccess.run();
                });
            }
        },"order1886-task").start();
    }
    private void writeError(Exception e){
        try(FileOutputStream out=new FileOutputStream(logFile,true)){
            out.write(("\nLauncher error: "+e+"\n").getBytes(StandardCharsets.UTF_8));
        }catch(IOException ignored){}
    }
    private void prepareGame(){
        if(gameDir==null){show("Instale um PKG ou selecione a pasta do jogo primeiro.");return;}
        if(!filePermission() && gameDir.getAbsolutePath().startsWith("/storage/emulated")){
            pendingStorage=REQ_FOLDER;requestStorage();return;
        }
        runTask("Preparando The Order no Android...",this::doPrepare);
    }
    private void doPrepare()throws Exception{
        if(gameDir==null)throw new IOException("Nenhum jogo selecionado");
        // The default Adreno Turnip is installed from the signed APK before running.
        if(Order1886DriverStore.BUNDLED.equals(drivers.selected())){
            show("Instalando Turnip GameHub 26.3 embutida...");
            drivers.ensureBundledDefault();
        }
        preparer.prepare(gameDir,prefs().getInt("fps",30),
                prefs().getString("aspect","original"),prefs().getInt("width",1920),
                prefs().getString("readback","relaxed"),
                prefs().getInt("language",1),disabledEffects(),this::show);
        if(!prefs().edit().putString("preparedSignature",prepSignature()).commit())
            throw new IOException("Não foi possível salvar perfil preparado");
        show("Jogo preparado no Android. Pronto para tentar iniciar.");
    }
    private void exportSaves(){
        if(gameOpen||working.get()){show("Feche o jogo e termine a operacao anterior.");return;}
        Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("application/zip");
        i.putExtra(Intent.EXTRA_TITLE,"TheOrder1886-saves.zip");
        i.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        startActivityForResult(i,REQ_SAVE_EXPORT);
    }
    private void importSaves(){
        if(gameOpen||working.get()){show("Feche o jogo e termine a operacao anterior.");return;}
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("application/zip");
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        startActivityForResult(i,REQ_SAVE_IMPORT);
    }
    private void exportLog(){
        if(!logFile.isFile()){show("Nenhum log gerado.");return;}
        Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("text/plain");
        i.putExtra(Intent.EXTRA_TITLE,"TheOrder1886-Android-log.txt");
        startActivityForResult(i,REQ_EXPORT);
    }
    private File nativeProbe(){
        return new File(getApplicationInfo().nativeLibraryDir,"liborder1886_probe.so");
    }
    private ProcessBuilder command(String...argv)throws Exception{
        if(!nativeProbe().isFile())throw new IOException("Runtime não encontrado no APK");
        ArrayList<String> args=new ArrayList<>();args.add(nativeProbe().getAbsolutePath());
        Collections.addAll(args,argv);
        ProcessBuilder b=new ProcessBuilder(args).directory(base).redirectErrorStream(true);
        Map<String,String> env=b.environment();
        env.put("LD_LIBRARY_PATH",getApplicationInfo().nativeLibraryDir);
        env.put("HOME",base.getAbsolutePath());env.put("TMPDIR",getCacheDir().getAbsolutePath());
        env.put("ORDER1886_PAD_FILE",new File(base,"pad.state").getAbsolutePath());
        env.put("ORDER1886_AUDIO_FIFO",new File(base,"audio.fifo").getAbsolutePath());
        env.put("ORDER1886_PRESENT_SOCKET",new File(base,"present.sock").getAbsolutePath());
        env.put("ORDER1886_GPU_USER_DIR",new File(base,"gpu-cache").getAbsolutePath());
        env.put("ORDER1886_READBACKS",Integer.toString(
            "precise".equals(prefs().getString("readback","relaxed"))?2:
            "selective".equals(prefs().getString("readback","relaxed"))?3:1));
        env.put("ORDER1886_VSYNC",prefs().getBoolean("vsync",false)?"1":"0");
        env.put("ORDER1886_BACKGROUND_WARMUP",prefs().getBoolean("warmup",false)?"1":"0");
        env.put("ORDER1886_DISPLAY_HZ",
            Integer.toString(Math.round(getWindowManager().getDefaultDisplay().getRefreshRate())));
        if(surface!=null&&surface.getWidth()>=320&&surface.getHeight()>=180) {
            final int physicalW=surface.getWidth(), physicalH=surface.getHeight();
            // The selected render resolution also determines the Android AHardwareBuffer
            // resolution. SurfaceFlinger alone upscales from e.g. 1280x720 to the device.
            // Preserve the 16:9 buffer (including the game's cinematic letterboxing);
            // Fit/Fill is still handled by order1886present through ASurfaceTransaction.
            final int[] output=Order1886OutputSize.forSurface(
                physicalW,physicalH,prefs().getInt("width",1920));
            env.put("ORDER1886_SCREEN_W",Integer.toString(output[0]));
            env.put("ORDER1886_SCREEN_H",Integer.toString(output[1]));
            android.util.Log.i("TheOrder1886","AHardwareBuffer "+
                output[0]+"x"+output[1]+"; Android compositor to "+
                physicalW+"x"+physicalH+" (render width "+
                prefs().getInt("width",1920)+")");
        }
        env.put("ORDER1886_GAME_PROFILE","order1886");
        Order1886LauncherConfig.environment(this,new File(base,"user"),env);
        drivers.configure(env);return b;
    }
    private void diagnose(){
        runTask("Verificando runtime e arquitetura...",()->{
            StringBuilder report=new StringBuilder();
            for(String opt:new String[]{"--runtime-info","--cpu-features"}){
                Process p=command(opt).start();
                try(BufferedReader rd=new BufferedReader(new InputStreamReader(p.getInputStream(),StandardCharsets.UTF_8))){
                    String line;while((line=rd.readLine())!=null)report.append(line).append('\n');
                }
                report.append("exit=").append(p.waitFor()).append('\n');
            }
            try(FileOutputStream out=new FileOutputStream(logFile,true)){
                out.write(report.toString().getBytes(StandardCharsets.UTF_8));
            }
            show("Diagnóstico concluído:\n"+report.substring(Math.max(0,report.length()-300)));
        });
    }
    private void startGame(){
        if(working.get()||gameOpen){show("Termine a tarefa anterior.");return;}
        if(gameDir==null||!isGame(gameDir)){show("Selecione ou instale o jogo.");return;}
        File image=currentImage();
        if(image==null){
            runTask("Preparando automaticamente antes de iniciar...",this::doPrepare,this::startGame);
            return;
        }
        if(!filePermission()&&gameDir.getAbsolutePath().startsWith("/storage/emulated")){
            show("Conceda acesso aos arquivos primeiro.");requestStorage();return;
        }
        mainUI.setVisibility(View.GONE);
        gameFrame.setVisibility(View.VISIBLE);
        gameOpen=true;stopped=false;
        if(Build.VERSION.SDK_INT>=29)gameFrame.post(()->{
            if(!gameOpen || gameFrame.getWidth()==0)return;
            int w=gameFrame.getWidth(), h=gameFrame.getHeight();
            // Keep a 180dp mid-right band free of the system Back interceptor.
            gameFrame.setSystemGestureExclusionRects(
                Collections.singletonList(new android.graphics.Rect(
                    w-dp(38),Math.max(0,h/2-dp(90)),w,
                    Math.min(h,h/2+dp(90)))));
        });
        setGameImmersive(true);
        setupTouchControls();
        applyHudStyle();
        previousFrameCount=0;previousFpsMs=0;
        fpsSmoothed=-1f;
        if(gameHud!=null)gameHud.setText("— FPS");
        main.removeCallbacks(fpsPoll);main.postDelayed(fpsPoll,500);
        main.postDelayed(()->{
            if(!gameOpen)return;
            if(!surface.getHolder().getSurface().isValid()){
                new AlertDialog.Builder(this).setMessage("Surface do Android não iniciou.")
                    .setPositiveButton("OK",(dialog,which)->stopGame()).show();
                return;
            }
            try {
                String msg=Order1886Present.start(surface.getHolder(),
                    new File(base,"present.sock").getAbsolutePath(),
                    prefs().getBoolean("fullscreen",false));
                if(!msg.startsWith("bridge running:"))throw new IOException(msg);
                presentStarted=true;
                pad.reset();
                pad.setRightStickZRZ(prefs().getBoolean("rightStickZRZ",false));
                launchNative(image);
            }catch(Throwable ex){show("Erro ao iniciar display: "+ex);stopGame();}
        },160);
    }
    private void launchNative(File image){
        if(!working.compareAndSet(false,true)){stopGame();return;}
        new Thread(()->{
            try {
                audio.start();
                if(!audio.awaitReady(5000))throw new IOException("AudioBridge indisponível");
                Order1886LauncherConfig.write(this,new File(base,"user"));
                invalidateOldSrtShaders();
                Process p=command(image.getAbsolutePath(),"--app0",gameDir.getAbsolutePath(),
                    "--user",new File(base,"user").getAbsolutePath(),"--timeout","0").start();
                game=p;
                show("Jogo executando no runtime Bionic. Logs ativos.");
                try(BufferedReader input=new BufferedReader(new InputStreamReader(p.getInputStream(),StandardCharsets.UTF_8));
                    BufferedWriter log=new BufferedWriter(new OutputStreamWriter(new FileOutputStream(logFile),StandardCharsets.UTF_8))){
                    String line;int n=0;
                    try {log.write("ORDER1886_PREPARED_MANIFEST "+preparer.manifestSummary());log.newLine();}
                    catch(Exception ex){log.write("ORDER1886_PREPARED_MANIFEST unavailable: "+ex.getMessage());log.newLine();}
                    while((line=input.readLine())!=null){
                        log.write(line);log.newLine();if(++n%30==0){log.flush();show("Log "+n+": "+line);}
                    }
                }
                int exit=p.waitFor();
                if(!stopped)show("Runtime encerrou com código "+exit+". Exporte o log.");
            }catch(Exception e){writeError(e);if(!stopped)show("Execução falhou: "+e);}
            finally{
                game=null;working.set(false);audio.stop();
                main.post(()->{if(gameOpen)stopGame();});
            }
        },"order1886-runtime").start();
    }
    // A single canvas-based PlayStation overlay replaces 18 independent Android buttons.
    private void setupTouchControls(){
        if(touchLayer==null)return;
        touchLayer.release();
        touchLayer.setAlpha(Math.max(.35f,Math.min(1f,
            prefs().getInt("controlOpacity",78)/100f)));
        touchLayer.setVisibility(prefs().getBoolean("onscreen",true)?View.VISIBLE:View.GONE);
        touchLayer.invalidate();
    }
    private void stopGame(){
        stopped=true;
        Process p=game;
        if(p!=null){p.destroy();p.destroyForcibly();game=null;}
        if(audio!=null)audio.stop();
        if(pad!=null)pad.reset();
        if(presentStarted){
            try{Order1886Present.stop();}catch(Throwable ignored){}
            presentStarted=false;
        }
        if(gameMenuDialog!=null){gameMenuDialog.dismiss();gameMenuDialog=null;}
        if(touchLayer!=null)touchLayer.release();
        editingControls=false;swipeCandidate=false;swipeConsumed=false;
        main.removeCallbacks(fpsPoll);
        gameOpen=false;gameFrame.setVisibility(View.GONE);mainUI.setVisibility(View.VISIBLE);
        setGameImmersive(false);
        render();
    }
    @Override public boolean dispatchTouchEvent(MotionEvent event){
        // Reversed from TLOU's left-edge swipe: drag from right to left.
        // Observe before the overlay receives input; cancel its active touch
        // sequence if the gesture becomes a menu swipe.
        if(!gameOpen || editingControls)return super.dispatchTouchEvent(event);
        final int action=event.getActionMasked();
        if(action==MotionEvent.ACTION_DOWN){
            swipeX=event.getX();swipeY=event.getY();
            swipeCandidate=event.getPointerCount()==1 &&
                swipeX>=gameFrame.getWidth()-dp(36);
            swipeConsumed=false;
        }else if(action==MotionEvent.ACTION_POINTER_DOWN){
            swipeCandidate=false;
        }else if(action==MotionEvent.ACTION_MOVE && swipeCandidate &&
                event.getPointerCount()==1 && !swipeConsumed){
            float dx=swipeX-event.getX();
            float dy=Math.abs(event.getY()-swipeY);
            if(dy>dp(52) || dx < -dp(20)){
                swipeCandidate=false;
            }else if(dx>=dp(62) && dx>dy*1.5f){
                swipeCandidate=false;
                swipeConsumed=true;
                MotionEvent cancel=MotionEvent.obtain(event);
                cancel.setAction(MotionEvent.ACTION_CANCEL);
                super.dispatchTouchEvent(cancel);
                cancel.recycle();
                showGameMenu();
                return true;
            }
        }
        if(swipeConsumed){
            if(action==MotionEvent.ACTION_UP || action==MotionEvent.ACTION_CANCEL)
                swipeConsumed=false;
            return true;
        }
        if(action==MotionEvent.ACTION_UP || action==MotionEvent.ACTION_CANCEL)
            swipeCandidate=false;
        return super.dispatchTouchEvent(event);
    }
    @Override public boolean dispatchKeyEvent(KeyEvent e){
        if(pad!=null&&pad.key(e))return true;
        return super.dispatchKeyEvent(e);
    }
    @Override public boolean onGenericMotionEvent(MotionEvent e){
        if(pad!=null&&e.isFromSource(InputDevice.SOURCE_JOYSTICK)&&pad.motion(e))return true;
        return super.onGenericMotionEvent(e);
    }
    @Override public void onBackPressed(){
        // Android reserves the right edge for Back on some system configurations.
        // That gesture must open the SAME in-game menu, never a direct exit prompt.
        if(gameOpen){
            if(editingControls && touchLayer!=null){
                touchLayer.finishEdit();
            }else showGameMenu();
        }else if(page!=0){page=0;render();}
        else super.onBackPressed();
    }
    @Override protected void onPause(){super.onPause();if(audio!=null)audio.pause();}
    @Override protected void onResume(){
        super.onResume();
        if(audio!=null)audio.resume();
        if(gameOpen)main.postDelayed(()->{if(gameOpen)setGameImmersive(true);},120);
    }
    @Override protected void onDestroy(){stopGame();main.removeCallbacksAndMessages(null);super.onDestroy();}
}
