package ro.cobrabm.fexdroid;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.ActivityInfo;
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
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Map;

/** Isolated The Order: 1886 Bionic boot-test. No God of War III launcher/runtime is used. */
public final class Order1886Activity extends Activity {
    private static final int PICK_BOOT=101, EXPORT_LOG=102;
    private final Handler ui=new Handler(Looper.getMainLooper());
    private File base, boot, logFile;
    private SurfaceView surface;
    private EditText app0Field;
    private TextView status;
    private Order1886PadBridge pad;
    private Order1886AudioBridge audio;
    private volatile Process game;
    private volatile boolean stopped=true;
    private Thread runner;
    private boolean presentStarted;

    private void show(String message) {
        ui.post(() -> { if (status != null) status.setText(message); });
    }
    private Button action(String name, View.OnClickListener handler) {
        Button b=new Button(this);
        b.setText(name);
        b.setOnClickListener(handler);
        return b;
    }
    private File nativeProbe() {
        return new File(getApplicationInfo().nativeLibraryDir, "liborder1886_probe.so");
    }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
        getWindow().addFlags(128); // KEEP_SCREEN_ON
        base=new File(getFilesDir(),"order1886");
        if (!base.exists()) base.mkdirs();
        boot=new File(base,"game.ps4boot5");
        logFile=new File(base,"last-runtime.log");
        pad=new Order1886PadBridge(new File(base,"pad.state"));
        audio=new Order1886AudioBridge(new File(base,"audio.fifo"));

        LinearLayout root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(0xff101012);
        LinearLayout row=new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(action("Importar PS4BOOT5",v -> selectBoot()));
        row.addView(action("Diagnóstico",v -> diagnose()));
        row.addView(action("Iniciar",v -> startGame()));
        row.addView(action("Parar",v -> stopGame()));
        row.addView(action("Exportar log",v -> exportLog()));
        root.addView(row);
        app0Field=new EditText(this);
        app0Field.setSingleLine(true);
        app0Field.setTextColor(0xffffffff);
        app0Field.setHintTextColor(0xffbbbbbb);
        app0Field.setHint("Pasta extraída com sce_sys/param.sfo (caminho completo)");
        app0Field.setText(getPreferences(0).getString("app0","/storage/emulated/0/TheOrder1886/CUSA00076"));
        root.addView(app0Field);
        surface=new SurfaceView(this);
        root.addView(surface,new LinearLayout.LayoutParams(-1,0,1f));
        status=new TextView(this);
        status.setTextColor(0xffeadcc4);
        status.setTextSize(13);
        status.setPadding(12,6,12,8);
        root.addView(status);
        setContentView(root);
        show("The Order: 1886 | ARM64 Bionic boot-test. "+
             (boot.isFile() ? "Imagem preparada importada." : "Importe uma imagem PS4BOOT5 preparada no PC.")+
             " Runtime: "+(nativeProbe().isFile() ? "presente" : "AUSENTE"));
    }
    private void selectBoot() {
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        startActivityForResult(i,PICK_BOOT);
    }
    private void exportLog() {
        if (!logFile.isFile()) { show("Ainda não existe log para exportar."); return; }
        Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("text/plain");
        i.putExtra(Intent.EXTRA_TITLE,"TheOrder1886-Android-log.txt");
        startActivityForResult(i,EXPORT_LOG);
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if (result!=RESULT_OK || data==null || data.getData()==null) return;
        Uri uri=data.getData();
        if (request==PICK_BOOT) {
            show("Importando arquivo preparado...");
            new Thread(() -> {
                File part=new File(base,"game.ps4boot5.part");
                try (InputStream in=getContentResolver().openInputStream(uri);
                     OutputStream out=new FileOutputStream(part)) {
                    if (in==null) throw new java.io.IOException("Sem acesso ao arquivo");
                    byte[] header=new byte[8];
                    int received=0;
                    while (received<header.length) {
                        int n=in.read(header,received,header.length-received);
                        if(n<0) break;
                        received+=n;
                    }
                    if (received!=8 || !new String(header,StandardCharsets.US_ASCII).equals("PS4BOOT5"))
                        throw new java.io.IOException("Arquivo não é PS4BOOT5; prepare o jogo no PC");
                    out.write(header);
                    byte[] chunk=new byte[1024*1024];
                    int n;
                    while((n=in.read(chunk))!=-1) out.write(chunk,0,n);
                    out.flush();
                    if(boot.exists() && !boot.delete()) throw new java.io.IOException("Não foi possível substituir imagem");
                    if(!part.renameTo(boot)) throw new java.io.IOException("Não foi possível ativar imagem");
                    show("Imagem PS4BOOT5 importada ("+(boot.length()/1024/1024)+" MB).");
                } catch(Exception e) { part.delete(); show("Falha na importação: "+e.getMessage()); }
            },"order1886-import").start();
        } else if (request==EXPORT_LOG) {
            try (InputStream in=new FileInputStream(logFile);
                 OutputStream out=getContentResolver().openOutputStream(uri)) {
                if(out==null) throw new java.io.IOException("Sem acesso ao destino");
                byte[] buf=new byte[16384]; int n;
                while((n=in.read(buf))!=-1) out.write(buf,0,n);
                show("Log exportado.");
            } catch(Exception e) { show("Exportação falhou: "+e.getMessage()); }
        }
    }
    private ProcessBuilder process(String... argv) throws Exception {
        if(!nativeProbe().isFile()) throw new java.io.IOException("Runtime ARM64 ausente do APK");
        ArrayList<String> args=new ArrayList<>();
        args.add(nativeProbe().getAbsolutePath());
        for(String a:argv) args.add(a);
        ProcessBuilder b=new ProcessBuilder(args).directory(base).redirectErrorStream(true);
        Map<String,String> env=b.environment();
        env.put("LD_LIBRARY_PATH",getApplicationInfo().nativeLibraryDir);
        env.put("HOME",base.getAbsolutePath());
        env.put("TMPDIR",getCacheDir().getAbsolutePath());
        env.put("ORDER1886_PAD_FILE",new File(base,"pad.state").getAbsolutePath());
        env.put("ORDER1886_AUDIO_FIFO",new File(base,"audio.fifo").getAbsolutePath());
        env.put("ORDER1886_PRESENT_SOCKET",new File(base,"present.sock").getAbsolutePath());
        return b;
    }
    private void diagnose() {
        if (runner!=null && runner.isAlive()) { show("Finalize a execução anterior."); return; }
        runner=new Thread(() -> {
            try {
                Process p=process("--runtime-info").start();
                try(BufferedReader in=new BufferedReader(new InputStreamReader(p.getInputStream(),StandardCharsets.UTF_8))) {
                    StringBuilder data=new StringBuilder(); String l;
                    while((l=in.readLine())!=null) data.append(l).append('\n');
                    int exit=p.waitFor();
                    show("Diagnóstico (código "+exit+"):\n"+data);
                }
            } catch(Exception e) { show("Diagnóstico falhou: "+e.getMessage()); }
        },"order1886-diagnostics");
        runner.start();
    }
    private void startGame() {
        if(runner!=null && runner.isAlive()) { show("Já existe uma execução ativa."); return; }
        if(!boot.isFile()) { show("Importe primeiro a imagem PS4BOOT5 preparada no PC."); return; }
        String app0=app0Field.getText().toString().trim();
        if(!new File(app0,"sce_sys/param.sfo").isFile()) {
            show("Pasta inválida ou sem permissão: "+app0+
                 " (precisa conter sce_sys/param.sfo).");
            return;
        }
        if(Build.VERSION.SDK_INT>=30 && !Environment.isExternalStorageManager() &&
           app0.startsWith("/storage/")) {
            show("Conceda acesso a todos os arquivos nas configurações e inicie novamente.");
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                        Uri.parse("package:"+getPackageName())));
            } catch(Exception ignored) {}
            return;
        }
        if(!surface.getHolder().getSurface().isValid()) { show("Surface ainda não pronta."); return; }
        getPreferences(0).edit().putString("app0",app0).apply();
        try {
            String present=Order1886Present.start(surface.getHolder(),
                    new File(base,"present.sock").getAbsolutePath(),false);
            if(!present.startsWith("bridge running:")) { show("Erro Surface: "+present); return; }
            presentStarted=true;
        } catch(Throwable e) { show("Falha AHardwareBuffer: "+e); return; }
        stopped=false;
        pad.reset();
        runner=new Thread(() -> {
            try {
                audio.start();
                if(!audio.awaitReady(5000)) throw new java.io.IOException("AudioBridge não ficou pronto");
                Process p=process(boot.getAbsolutePath(),"--app0",app0,
                        "--user",new File(base,"user").getAbsolutePath(),"--timeout","0").start();
                game=p;
                show("The Order iniciado no runtime ARM64. Coletando logs...");
                try (BufferedReader reader=new BufferedReader(
                         new InputStreamReader(p.getInputStream(),StandardCharsets.UTF_8));
                     BufferedWriter log=new BufferedWriter(
                         new OutputStreamWriter(new FileOutputStream(logFile),StandardCharsets.UTF_8))) {
                    String line; int count=0;
                    while((line=reader.readLine())!=null) {
                        log.write(line); log.newLine();
                        if(++count%25==0) { log.flush(); show("Linhas de log: "+count+" | último: "+line); }
                    }
                    log.flush();
                }
                int exit=p.waitFor();
                if(!stopped) show("Runtime encerrou com código "+exit+"; veja/exporte o log.");
            } catch(Exception e) { if(!stopped) show("Falha no runtime: "+e+"; log: "+logFile); }
            finally {
                game=null;
                audio.stop();
                stopped=true;
            }
        },"order1886-runner");
        runner.start();
    }
    private void stopGame() {
        stopped=true;
        Process p=game;
        if(p!=null) { p.destroy(); p.destroyForcibly(); game=null; }
        if(audio!=null) audio.stop();
        if(pad!=null) pad.reset();
        if(presentStarted) {
            try { Order1886Present.stop(); } catch(Throwable ignored) {}
            presentStarted=false;
        }
        show("Execução interrompida.");
    }
    @Override public boolean dispatchKeyEvent(KeyEvent e) {
        if(pad!=null && pad.key(e)) return true;
        return super.dispatchKeyEvent(e);
    }
    @Override public boolean onGenericMotionEvent(MotionEvent e) {
        if(pad!=null && e.isFromSource(InputDevice.SOURCE_JOYSTICK) && pad.motion(e)) return true;
        return super.onGenericMotionEvent(e);
    }
    @Override protected void onPause() { super.onPause(); if(audio!=null) audio.pause(); }
    @Override protected void onResume() { super.onResume(); if(audio!=null) audio.resume(); }
    @Override protected void onDestroy() { stopGame(); super.onDestroy(); }
}
