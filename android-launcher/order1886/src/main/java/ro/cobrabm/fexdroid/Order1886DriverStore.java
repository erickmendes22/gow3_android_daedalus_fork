package ro.cobrabm.fexdroid;

import android.content.Context;
import android.net.Uri;
import android.os.Build;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

/** Driver selection for The Order (NOT the GoW3 GOW3_VULKAN_DRIVER setting). */
final class Order1886DriverStore {
    private final Context context;
    private final File root;
    Order1886DriverStore(Context c) { context=c;root=new File(c.getFilesDir(),"gpu-drivers"); }
    private android.content.SharedPreferences prefs(){
        return context.getSharedPreferences("order1886",Context.MODE_PRIVATE);
    }
    String selected() {return prefs().getString("driver","system");}
    List<DriverArchive.Installed> installed(){
        ArrayList<DriverArchive.Installed> entries=new ArrayList<>();
        File[] folders=root.listFiles();
        if(folders!=null)for(File f:folders)if(f.isDirectory()&&f.getName().matches("[0-9a-f]{64}")){
            try {entries.add(DriverArchive.read(root,f.getName(),Build.VERSION.SDK_INT));}
            catch(IOException ignored){}
        }
        entries.sort(Comparator.comparing(a->a.name,String.CASE_INSENSITIVE_ORDER));
        return entries;
    }
    void select(String value) throws Exception {
        if(!"system".equals(value) && !value.startsWith("custom:"))
            throw new IOException("Driver desconhecido.");
        if(value.startsWith("custom:")) DriverArchive.read(root,value.substring(7),Build.VERSION.SDK_INT);
        if(!prefs().edit().putString("driver",value).commit())
            throw new IOException("Não foi possível salvar a seleção.");
    }
    DriverArchive.Installed importZip(Uri uri) throws Exception {
        try(InputStream in=context.getContentResolver().openInputStream(uri)){
            if(in==null)throw new IOException("Não foi possível abrir ZIP");
            DriverArchive.Installed result=DriverArchive.install(root,in,Build.VERSION.SDK_INT,meta->{
                JSONObject data=new JSONObject(new String(Files.readAllBytes(meta.toPath()),StandardCharsets.UTF_8));
                if(data.optInt("schemaVersion",-1)!=1)
                    throw new IOException("meta.json incompatível: não é pacote AdrenoTools válido.");
                return new DriverArchive.Metadata(data.getString("name"),
                    data.getString("libraryName"),data.getInt("minApi"));
            });
            select("custom:"+result.id);
            return result;
        }
    }
    String description(){
        String selection=selected();
        if("system".equals(selection))return "Vulkan do sistema";
        if(selection.startsWith("custom:")){
            try{return DriverArchive.read(root,selection.substring(7),Build.VERSION.SDK_INT).name;}
            catch(Exception ignored){return "Driver removido/inválido";}
        }
        return selection;
    }
    void configure(Map<String,String> env) throws Exception {
        String selection=selected();
        env.remove("ORDER1886_VULKAN_DRIVER");
        if("system".equals(selection))return;
        DriverArchive.Installed driver=DriverArchive.read(root,selection.substring(7),Build.VERSION.SDK_INT);
        DriverArchive.validateLibrary(driver.library);
        env.put("ORDER1886_VULKAN_DRIVER",driver.library.getAbsolutePath());
        String previous=env.get("LD_LIBRARY_PATH");
        env.put("LD_LIBRARY_PATH",previous+":"+driver.library.getParent());
    }
}
