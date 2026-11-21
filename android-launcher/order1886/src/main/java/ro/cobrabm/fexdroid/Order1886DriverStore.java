package ro.cobrabm.fexdroid;

import android.content.Context;
import android.net.Uri;
import android.os.Build;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

/** Dedicated Order driver storage; does not change settings of other emulator apps. */
final class Order1886DriverStore {
    static final String BUNDLED="bundled";
    static final String BUNDLED_NAME="GameHub Turnip 26.3 + DD GMEM + PWR_MAX (Experimental)";
    static final String BUNDLED_ASSET="order1886-turnip-default.zip";
    private final Context context;
    private final File root;
    Order1886DriverStore(Context c) { context=c;root=new File(c.getFilesDir(),"gpu-drivers"); }
    private android.content.SharedPreferences prefs(){
        return context.getSharedPreferences("order1886",Context.MODE_PRIVATE);
    }
    private static boolean adrenoDevice(){
        if(new File("/sys/class/kgsl/kgsl-3d0").exists())return true;
        if(Build.VERSION.SDK_INT>=31&&"qualcomm".equalsIgnoreCase(Build.SOC_MANUFACTURER))return true;
        String hardware=Build.HARDWARE.toLowerCase(Locale.ROOT);
        return hardware.contains("qcom")||hardware.contains("qualcomm");
    }
    /** Auto-default to the bundled Turnip on Adreno; other GPUs retain system Vulkan. */
    String selected(){return prefs().getString("driver",adrenoDevice()?BUNDLED:"system");}
    private static DriverArchive.Metadata metadata(File meta) throws Exception {
        JSONObject json=new JSONObject(new String(Files.readAllBytes(meta.toPath()),StandardCharsets.UTF_8));
        if(json.optInt("schemaVersion",-1)!=1)
            throw new IOException("meta.json não é pacote AdrenoTools válido");
        return new DriverArchive.Metadata(json.getString("name"),
            json.getString("libraryName"),json.getInt("minApi"));
    }
    /** Asset is shipped with the APK; no user download or network access required. */
    synchronized DriverArchive.Installed ensureBundledDefault() throws Exception {
        String id=prefs().getString("bundledTurnipId","");
        if(id.matches("[0-9a-f]{64}")){
            try{
                DriverArchive.Installed driver=DriverArchive.read(root,id,Build.VERSION.SDK_INT);
                DriverArchive.validateLibrary(driver.library);
                return driver;
            }catch(IOException ignored){/* Deleted/incomplete installation: restore asset. */}
        }
        try(InputStream in=context.getAssets().open(BUNDLED_ASSET)){
            DriverArchive.Installed driver=DriverArchive.install(root,in,Build.VERSION.SDK_INT,
                Order1886DriverStore::metadata);
            if(!prefs().edit().putString("bundledTurnipId",driver.id).commit())
                throw new IOException("Falha ao salvar driver padrão");
            return driver;
        }
    }
    List<DriverArchive.Installed> installed(){
        ArrayList<DriverArchive.Installed> results=new ArrayList<>();
        File[] dirs=root.listFiles();
        if(dirs!=null)for(File dir:dirs)if(dir.isDirectory()&&dir.getName().matches("[0-9a-f]{64}")){
            try{results.add(DriverArchive.read(root,dir.getName(),Build.VERSION.SDK_INT));}
            catch(IOException ignored){}
        }
        results.sort(Comparator.comparing(d->d.name,String.CASE_INSENSITIVE_ORDER));
        return results;
    }
    void select(String value) throws Exception {
        if(!"system".equals(value)&&!BUNDLED.equals(value)&&!value.startsWith("custom:"))
            throw new IOException("Driver desconhecido");
        if(BUNDLED.equals(value)&&!adrenoDevice())
            throw new IOException("Turnip requer GPU Qualcomm Adreno");
        if(value.startsWith("custom:"))
            DriverArchive.read(root,value.substring(7),Build.VERSION.SDK_INT);
        if(!prefs().edit().putString("driver",value).commit())
            throw new IOException("Falha ao salvar driver selecionado");
    }
    DriverArchive.Installed importZip(Uri uri) throws Exception {
        try(InputStream in=context.getContentResolver().openInputStream(uri)){
            if(in==null)throw new IOException("Não foi possível abrir ZIP");
            DriverArchive.Installed driver=DriverArchive.install(root,in,Build.VERSION.SDK_INT,
                Order1886DriverStore::metadata);
            select("custom:"+driver.id);
            return driver;
        }
    }
    String description(){
        String choice=selected();
        if(BUNDLED.equals(choice))return BUNDLED_NAME+" (padrão)";
        if("system".equals(choice))return "Vulkan do sistema";
        if(choice.startsWith("custom:")){
            try{return DriverArchive.read(root,choice.substring(7),Build.VERSION.SDK_INT).name;}
            catch(IOException ignored){return "Driver personalizado removido/inválido";}
        }
        return choice;
    }
    void configure(Map<String,String> env) throws Exception {
        String choice=selected();
        env.remove("ORDER1886_VULKAN_DRIVER");
        if("system".equals(choice))return;
        DriverArchive.Installed driver=BUNDLED.equals(choice)
            ?ensureBundledDefault():DriverArchive.read(root,choice.substring(7),Build.VERSION.SDK_INT);
        DriverArchive.validateLibrary(driver.library);
        env.put("ORDER1886_VULKAN_DRIVER",driver.library.getAbsolutePath());
        String previous=env.get("LD_LIBRARY_PATH");
        env.put("LD_LIBRARY_PATH",(previous==null||previous.isEmpty()?"":previous+":")+
                driver.library.getParent());
    }
}
