package ro.cobrabm.fexdroid;

import android.content.Context;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Prepares the original title's PS4BOOT5 image on Android using its own PC-port Python scripts. */
final class Order1886Preparation {
    interface Progress { void update(String progress); }
    private final Context context;
    private final File tools, state;
    Order1886Preparation(Context c, File state) {
        context=c; this.state=state; tools=new File(c.getFilesDir(),"order1886-toolchain-v2");
    }
    File image(){return new File(state,"prepared/boot-linked.bin");}
    private File interpreter(){
        return new File(context.getApplicationInfo().nativeLibraryDir,"liborder1886_python.so");
    }
    private static boolean valid(File image){
        if(!image.isFile()||image.length()<100)return false;
        try(FileInputStream in=new FileInputStream(image)){
            byte[] b=new byte[8];return in.read(b)==8 && "PS4BOOT5".equals(new String(b,StandardCharsets.US_ASCII));
        }catch(IOException e){return false;}
    }
    boolean prepared(){return valid(image());}
    private File script(){return new File(tools,"order1886/order1886.py");}
    private void installToolchain(Progress progress) throws Exception {
        if(script().isFile()&&new File(tools,"python/lib/python3.13/os.py").isFile())return;
        progress.update("Preparando bibliotecas Python ARM64 no armazenamento privado...");
        if(!interpreter().isFile())throw new IOException("Python ARM64 não incluído neste APK");
        // No game assets, no executables from untrusted archives: only the signed APK asset.
        File marker=new File(tools,".installed");
        try(InputStream file=context.getAssets().open("order1886-toolchain.zip");
            ZipInputStream zip=new ZipInputStream(new BufferedInputStream(file))){
            if(!tools.isDirectory()&&!tools.mkdirs())throw new IOException("Não foi possível criar runtime Python");
            byte[] buffer=new byte[65536];
            ZipEntry entry;int count=0;long total=0;
            while((entry=zip.getNextEntry())!=null){
                if(++count>5000)throw new IOException("Bibliotecas Python excederam limite de arquivos");
                String name=entry.getName();
                if(name.startsWith("/")||name.contains("\\")||name.contains(":")||name.contains("../")||
                   name.equals("..")||name.endsWith("/.."))
                    throw new IOException("Caminho de runtime inválido");
                File target=new File(tools,name).getCanonicalFile();
                if(!target.getPath().startsWith(tools.getCanonicalPath()+File.separator))
                    throw new IOException("Caminho sai da pasta do aplicativo");
                if(entry.isDirectory()){if(!target.exists()&&!target.mkdirs())throw new IOException("mkdir: "+name);}
                else{
                    if(!target.getParentFile().isDirectory()&&!target.getParentFile().mkdirs())
                        throw new IOException("mkdir: "+name);
                    try(OutputStream out=new BufferedOutputStream(new FileOutputStream(target))){
                        int n;
                        while((n=zip.read(buffer))!=-1){
                            total+=n;
                            if(total>400L*1024*1024)throw new IOException("Runtime Python excede o tamanho permitido");
                            out.write(buffer,0,n);
                        }
                    }
                }
                zip.closeEntry();
                if(count%300==0)progress.update("Instalando bibliotecas de preparação: "+count+" arquivos");
            }
        }
        if(!script().isFile()||!new File(tools,"python/lib/python3.13/os.py").isFile())
            throw new IOException("Pacote Python incompleto");
        if(!marker.createNewFile()&&!marker.isFile())throw new IOException("Não foi possível registrar runtime Python");
    }

    void prepare(File game, int fps, String aspect, int renderWidth,
                 String readback, Progress progress) throws Exception {
        if(!new File(game,"eboot.bin").isFile() ||
           !new File(game,"sce_sys/param.sfo").isFile() ||
           !new File(game,"sce_module/libc.prx").isFile() ||
           !new File(game,"sce_module/libSceFios2.prx").isFile())
            throw new IOException("A pasta precisa conter eboot.bin, sce_sys/param.sfo, libc.prx e libSceFios2.prx.");
        installToolchain(progress);
        File py=interpreter();
        ArrayList<String> argv=new ArrayList<>();
        argv.add(py.getAbsolutePath());
        argv.add("-B");
        argv.add(script().getAbsolutePath());
        argv.add("--prepare-only");
        argv.add("--game-dir");argv.add(game.getAbsolutePath());
        argv.add("--state-dir");argv.add(state.getAbsolutePath());
        argv.add("--frame-rate");argv.add(Integer.toString(fps));
        argv.add("--aspect-ratio");argv.add(aspect);
        argv.add("--render-width");argv.add(Integer.toString(renderWidth));
        argv.add("--readbacks");argv.add(readback);
        ProcessBuilder builder=new ProcessBuilder(argv).directory(tools).redirectErrorStream(true);
        Map<String,String> env=builder.environment();
        env.put("PYTHONHOME",new File(tools,"python").getAbsolutePath());
        env.put("PYTHONPATH",new File(tools,"order1886").getAbsolutePath());
        env.put("PYTHONDONTWRITEBYTECODE","1");
        env.put("PYTHONUTF8","1");
        env.put("HOME",tools.getAbsolutePath());
        env.put("TMPDIR",context.getCacheDir().getAbsolutePath());
        env.put("LD_LIBRARY_PATH",context.getApplicationInfo().nativeLibraryDir);
        // Android /data/user/0 and /storage/emulated can be OS-managed symlink aliases.
        // Trust only these launcher-chosen prefixes; script still rejects links beneath them.
        env.put("ORDER1886_ANDROID_TRUSTED_GAME_ROOT",game.getAbsolutePath());
        env.put("ORDER1886_ANDROID_TRUSTED_STATE_ROOT",state.getAbsolutePath());
        progress.update("Preparando boot-linked.bin no Android (pode consumir memória)...");
        Process process=builder.start();
        StringBuilder last=new StringBuilder();
        try(BufferedReader reader=new BufferedReader(new InputStreamReader(process.getInputStream(),StandardCharsets.UTF_8))){
            String line;int n=0;
            while((line=reader.readLine())!=null){
                if(last.length()>15000)last.delete(0,last.length()-8000);
                last.append(line).append('\n');
                if(++n%8==0)progress.update("Preparação: "+line);
            }
        }
        int result=process.waitFor();
        if(result!=0||!valid(image()))
            throw new IOException("Preparação falhou (código "+result+"). "+last.substring(Math.max(0,last.length()-2700)));
        progress.update("PS4BOOT5 preparado no celular: "+(image().length()/1024/1024)+" MB");
    }
}
