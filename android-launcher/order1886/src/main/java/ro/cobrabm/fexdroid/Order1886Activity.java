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
                             REQ_STORAGE=117;
    private final Handler main=new Handler(Looper.getMainLooper());
    private final AtomicBoolean working=new AtomicBoolean();
    private File base,gameDir,logFile,manualBoot;
    private Order1886PadBridge pad;
    private Order1886AudioBridge audio;
    private Order1886Content content;
    private Order1886Preparation preparer;
    private Order1886DriverStore drivers;
    private FrameLayout screen, gameFrame, touchLayer;
    private LinearLayout mainUI,body,tabs;
    private SurfaceView surface;
    private TextView status,gameHud,gameTitle;
    private volatile Process game;
    private volatile boolean stopped=true;
    private boolean presentStarted, gameOpen;
    private int page=0, pendingStorage=0;
    private String statusText="Pronto para configurar o jogo.";
    private int leftX=128,leftY=128,rightX=128,rightY=128;
    private boolean virtualLeftActive,virtualRightActive;
    private final Set<String> virtualKeys=new LinkedHashSet<>();
    private long previousFrameCount;
    private final Runnable fpsPoll=new Runnable(){
        @Override public void run(){
            if(!gameOpen)return;
            try {
                long count=Order1886Present.framesIfLoaded();
                long delta=Math.max(0,count-previousFrameCount);
                previousFrameCount=count;
                if(gameHud!=null)gameHud.setText("FPS "+delta+"  |  "+drivers.description());
            }catch(Throwable ignored){}
            main.postDelayed(this,1000);
        }
    };

    private android.content.SharedPreferences prefs(){return getSharedPreferences("order1886",MODE_PRIVATE);}
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
        TextView v=new TextView(this);v.setText(text);v.setTextColor(color);
        v.setTextSize(sp);if(bold)v.setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        v.setIncludeFontPadding(false);return v;
    }
    private Button button(String name, boolean accent,View.OnClickListener listener){
        Button b=new Button(this);
        b.setAllCaps(false);b.setText(name);b.setTextSize(13);
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
        if(caption!=null){TextView t=label(caption.toUpperCase(Locale.ROOT),12,GOLD,true);c.addView(t);gap(c,9);}
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
        statusText=message;
        main.post(() -> {
            if(status!=null)status.setText(message);
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
        preparer=new Order1886Preparation(this,new File(base,"user"));
        drivers=new Order1886DriverStore(this);
        pad=new Order1886PadBridge(new File(base,"pad.state"));
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
        touchLayer=new FrameLayout(this);
        gameFrame.addView(touchLayer,new FrameLayout.LayoutParams(-1,-1));
        gameHud=label("FPS —",12,GOLD,true);
        gameHud.setBackground(shape(0xaa151b21,0,6));
        gameHud.setPadding(dp(8),dp(5),dp(8),dp(5));
        FrameLayout.LayoutParams hp=new FrameLayout.LayoutParams(-2,-2,Gravity.TOP|Gravity.RIGHT);
        hp.setMargins(0,dp(10),dp(15),0);
        gameFrame.addView(gameHud,hp);
        Button back=button("☰  MENU",false,v->new AlertDialog.Builder(this)
            .setTitle("The Order: 1886")
            .setItems(new String[]{"Voltar ao launcher (parar jogo)","Retomar","Exportar log"},
                      (dlg,i)->{if(i==0)stopGame();else if(i==2)exportLog();})
            .show());
        FrameLayout.LayoutParams bp=new FrameLayout.LayoutParams(dp(117),dp(43),Gravity.TOP|Gravity.LEFT);
        bp.setMargins(dp(13),dp(10),0,0);gameFrame.addView(back,bp);
        setContentView(screen);
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
        if(preparer.prepared())return preparer.image();
        return manualBoot.isFile()?manualBoot:null;
    }
    private String prepSignature(){
        return prefs().getInt("fps",30)+":"+
            prefs().getString("aspect","original")+":"+
            prefs().getInt("width",1920);
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
        ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,items);
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
        CheckBox box=new CheckBox(this);box.setText(label);box.setTextColor(WHITE);
        box.setChecked(prefs().getBoolean(key,def));
        box.setOnCheckedChangeListener((b,checked)->{
            prefs().edit().putBoolean(key,checked).apply();selectionChange();
        });
        card.addView(box);
    }
    private void renderGraphics(){
        LinearLayout c=card(body,"Configurações reais de vídeo");
        String[] fps={"30 FPS (padrão)","60 FPS (experimental)"};
        selectSpinner(c,"Taxa do jogo",fps,prefs().getInt("fps",30)==60?1:0,
            n->{prefs().edit().putInt("fps",n==0?30:60).apply();selectionChange();});
        String[] widths={"1920 (nativo)","1600","1280"};
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
        selectSpinner(c,"Idioma do jogo",new String[]{"Inglês","Português (Brasil)","Português (Portugal)"},
            prefs().getInt("language",1)==17?1:prefs().getInt("language",1)==7?2:0,
            n->{prefs().edit().putInt("language",n==1?17:n==2?7:1).apply();selectionChange();});
        toggle(c,"VSync", "vsync",false);
        toggle(c,"Shaders assíncronos", "asyncShaders",true);
        toggle(c,"Tela cheia / preencher a tela","fullscreen",false);
        toggle(c,"Controles virtuais","onscreen",true);
        toggle(c,"Aquecimento de shaders em segundo plano (experimental)","warmup",false);
        actions(c,button("Aplicar e preparar jogo",true,v->prepareGame()));
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
            "Sistema ou Turnip personalizado. Arquivos ZIP AdrenoTools com meta.json; "+
            "pacotes incompatíveis com ARM64 são recusados.");
        actions(c,button("Usar driver do sistema",false,v->{
            try{drivers.select("system");render();show("Vulkan do sistema selecionado.");}
            catch(Exception e){show(e.getMessage());}
        }),button("Importar Turnip ZIP",true,v->pickDriver()));
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
            "Para Snapdragon/Adreno, importe uma Turnip compatível com Android e com a sua GPU. "+
            "A seleção é persistida e aplicada na próxima inicialização. "+
            "Se falhar, volte para Driver do sistema.");
    }
    private void renderTools(){
        LinearLayout c=card(body,"Arquivos e diagnóstico");
        line(c,"Runtime ARM64",new File(getApplicationInfo().nativeLibraryDir,
            "liborder1886_probe.so").isFile()?"Bibliotecas nativas presentes":"Bibliotecas nativas ausentes");
        actions(c,button("Importar boot-linked.bin",false,v->selectFile(REQ_BOOT)),
                  button("Exportar log",false,v->exportLog()));
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
                    gameDir=dir;
                    prefs().edit().putString("gameDir",dir.getAbsolutePath())
                        .remove("preparedSignature").apply();
                    show("Pasta selecionada: "+dir.getName()+". Prepare o jogo para iniciar.");
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
                    prefs().edit().putString("gameDir",installed.getAbsolutePath()).remove("preparedSignature").apply();
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
    private void runTask(String beginning,Work task){
        if(!working.compareAndSet(false,true)){show("Operação anterior ainda ativa.");return;}
        show(beginning);
        new Thread(()->{
            try{task.perform();}
            catch(Exception e){writeError(e);show("Falha: "+e.getMessage());}
            finally{working.set(false);main.post(this::render);}
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
        preparer.prepare(gameDir,prefs().getInt("fps",30),
                prefs().getString("aspect","original"),prefs().getInt("width",1920),
                prefs().getString("readback","relaxed"),
                prefs().getInt("language",1),this::show);
        if(!prefs().edit().putString("preparedSignature",prepSignature()).commit())
            throw new IOException("Não foi possível salvar perfil preparado");
        show("Jogo preparado no Android. Pronto para tentar iniciar.");
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
            env.put("ORDER1886_SCREEN_W",Integer.toString(surface.getWidth()));
            env.put("ORDER1886_SCREEN_H",Integer.toString(surface.getHeight()));
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
        if(image==null){show("Prepare o jogo no Android antes de iniciar.");return;}
        String signature=prefs().getString("preparedSignature","");
        if(preparer.prepared()&&!prepSignature().equals(signature)){
            show("Configurações mudaram. Prepare novamente o jogo antes de iniciar.");
            return;
        }
        if(!filePermission()&&gameDir.getAbsolutePath().startsWith("/storage/emulated")){
            show("Conceda acesso aos arquivos primeiro.");requestStorage();return;
        }
        mainUI.setVisibility(View.GONE);
        gameFrame.setVisibility(View.VISIBLE);
        gameOpen=true;stopped=false;
        setGameImmersive(true);
        setupTouchControls();
        previousFrameCount=0;main.removeCallbacks(fpsPoll);main.postDelayed(fpsPoll,1000);
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
                Process p=command(image.getAbsolutePath(),"--app0",gameDir.getAbsolutePath(),
                    "--user",new File(base,"user").getAbsolutePath(),"--timeout","0").start();
                game=p;
                show("Jogo executando no runtime Bionic. Logs ativos.");
                try(BufferedReader input=new BufferedReader(new InputStreamReader(p.getInputStream(),StandardCharsets.UTF_8));
                    BufferedWriter log=new BufferedWriter(new OutputStreamWriter(new FileOutputStream(logFile),StandardCharsets.UTF_8))){
                    String line;int n=0;
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
    private void setupTouchControls(){
        touchLayer.removeAllViews();virtualKeys.clear();
        leftX=leftY=rightX=rightY=128;
        virtualLeftActive=virtualRightActive=false;
        if(!prefs().getBoolean("onscreen",true))return;
        addStick(true,Gravity.BOTTOM|Gravity.LEFT,dp(18),dp(16));
        addStick(false,Gravity.BOTTOM|Gravity.RIGHT,dp(18),dp(16));
        addTouchButton("L2","l2",Gravity.LEFT|Gravity.TOP,dp(18),dp(100));
        addTouchButton("L1","l1",Gravity.LEFT|Gravity.TOP,dp(88),dp(100));
        addTouchButton("R1","r1",Gravity.RIGHT|Gravity.TOP,dp(88),dp(100));
        addTouchButton("R2","r2",Gravity.RIGHT|Gravity.TOP,dp(18),dp(100));
        addTouchButton("△","triangle",Gravity.RIGHT|Gravity.BOTTOM,dp(100),dp(185));
        addTouchButton("○","circle",Gravity.RIGHT|Gravity.BOTTOM,dp(26),dp(137));
        addTouchButton("×","cross",Gravity.RIGHT|Gravity.BOTTOM,dp(100),dp(88));
        addTouchButton("□","square",Gravity.RIGHT|Gravity.BOTTOM,dp(178),dp(137));
        // The Order uses the D-pad for inventory/selection and L3/R3 for
        // analogue-stick clicks: expose the actual PS4 tokens used by PadBridge.
        addTouchButton("↑","up",Gravity.LEFT|Gravity.BOTTOM,dp(212),dp(112));
        addTouchButton("↓","down",Gravity.LEFT|Gravity.BOTTOM,dp(212),dp(13));
        addTouchButton("←","left",Gravity.LEFT|Gravity.BOTTOM,dp(155),dp(62));
        addTouchButton("→","right",Gravity.LEFT|Gravity.BOTTOM,dp(270),dp(62));
        addTouchButton("L3","l3",Gravity.LEFT|Gravity.BOTTOM,dp(58),dp(155));
        addTouchButton("R3","r3",Gravity.RIGHT|Gravity.BOTTOM,dp(58),dp(155));
        addTouchButton("OPTIONS","options",Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL,dp(82),dp(16));
        addTouchButton("TOUCH","touchpad",Gravity.TOP|Gravity.CENTER_HORIZONTAL,dp(82),dp(12));
    }
    private void addStick(boolean left,int gravity,int marginX,int marginY){
        TextView padView=label(left?"L":"R",22,0xffddc58c,true);
        padView.setGravity(Gravity.CENTER);
        padView.setBackground(shape(0x774b5360,0x779da4ad,100));
        FrameLayout.LayoutParams p=new FrameLayout.LayoutParams(dp(132),dp(132),gravity);
        if((gravity&Gravity.RIGHT)==Gravity.RIGHT)p.rightMargin=marginX;else p.leftMargin=marginX;
        p.bottomMargin=marginY;
        touchLayer.addView(padView,p);
        padView.setOnTouchListener((v,e)->{
            switch(e.getActionMasked()){
                case MotionEvent.ACTION_DOWN:case MotionEvent.ACTION_MOVE:{
                    float x=Math.max(-1,Math.min(1,(e.getX()-v.getWidth()/2f)/(v.getWidth()*.4f)));
                    float y=Math.max(-1,Math.min(1,(e.getY()-v.getHeight()/2f)/(v.getHeight()*.4f)));
                    int ax=Math.round(127.5f*(x+1)),ay=Math.round(127.5f*(y+1));
                    if(left){leftX=ax;leftY=ay;virtualLeftActive=true;}
                    else{rightX=ax;rightY=ay;virtualRightActive=true;}
                    sendVirtual();return true;
                }
                case MotionEvent.ACTION_CANCEL:case MotionEvent.ACTION_UP:
                    if(left){leftX=leftY=128;virtualLeftActive=false;}
                    else{rightX=rightY=128;virtualRightActive=false;}
                    sendVirtual();return true;
            }
            return true;
        });
    }
    private void addTouchButton(String text,String token,int gravity,int marginX,int marginY){
        TextView v=label(text,text.length()>3?10:18,WHITE,true);v.setGravity(Gravity.CENTER);
        v.setBackground(shape(0x99545966,0xaa9fa5ad,40));
        FrameLayout.LayoutParams p=new FrameLayout.LayoutParams(dp(text.length()>3?76:53),dp(49),gravity);
        if((gravity&Gravity.RIGHT)==Gravity.RIGHT)p.rightMargin=marginX;
        else if((gravity&Gravity.LEFT)==Gravity.LEFT)p.leftMargin=marginX;
        if((gravity&Gravity.BOTTOM)==Gravity.BOTTOM)p.bottomMargin=marginY;
        else p.topMargin=marginY;
        touchLayer.addView(v,p);
        v.setOnTouchListener((view,event)->{
            int action=event.getActionMasked();
            if(action==MotionEvent.ACTION_DOWN)virtualKeys.add(token);
            else if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL)virtualKeys.remove(token);
            sendVirtual();return true;
        });
    }
    private void sendVirtual(){
        if(pad!=null)pad.virtual(new LinkedHashSet<>(virtualKeys),leftX,leftY,rightX,rightY,
                virtualLeftActive,virtualRightActive,0,0);
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
        virtualKeys.clear();main.removeCallbacks(fpsPoll);
        gameOpen=false;gameFrame.setVisibility(View.GONE);mainUI.setVisibility(View.VISIBLE);
        setGameImmersive(false);
        render();
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
        if(gameOpen)new AlertDialog.Builder(this).setTitle("Sair do jogo?")
            .setMessage("Progresso não salvo será perdido.")
            .setPositiveButton("Parar", (dialog,which)->stopGame())
            .setNegativeButton("Retomar",null).show();
        else if(page!=0){page=0;render();}
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
