package ro.cobrabm.fexdroid;

import android.content.Context;
import android.net.Uri;
import android.os.Build;
import com.gow3.android.R;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

/** Launcher selection and launch environment for the Bionic ICD/HAL loader. */
public final class GpuDriverManager {
    private GpuDriverManager() {}
    public static boolean supported(Context context) { return "com.gow3.android.bionic".equals(context.getPackageName()) || SotcPaths.isSotc(context); }
    private static File root(Context context) { return new File(context.getFilesDir(),"gpu-drivers"); }
    public static String selected(Context context) {
        return context.getSharedPreferences(SotcPaths.prefsName(context),Context.MODE_PRIVATE).getString("gpu_driver","auto");
    }
    public static void select(Context context,String value) throws IOException {
        if (!supported(context)) throw new IOException("Custom drivers require the Bionic runtime");
        if (value.startsWith("custom:")) DriverArchive.read(root(context),value.substring(7),Build.VERSION.SDK_INT);
        else if (!Arrays.asList("auto","gen8","adreno7xx","system").contains(value)) throw new IOException("Invalid driver selection");
        if (!context.getSharedPreferences(SotcPaths.prefsName(context),Context.MODE_PRIVATE).edit().putString("gpu_driver",value).commit())
            throw new IOException("Cannot save driver selection");
    }
    public static List<DriverArchive.Installed> installed(Context context) {
        List<DriverArchive.Installed> result=new ArrayList<>(); File[] files=root(context).listFiles();
        if (files!=null) for (File file:files) if (file.isDirectory() && file.getName().matches("[0-9a-f]{64}")) {
            try { result.add(DriverArchive.read(root(context),file.getName(),Build.VERSION.SDK_INT)); }
            catch (IOException ignored) { /* Incomplete packages cannot be selected. */ }
        }
        result.sort(Comparator.comparing(d -> d.name,String.CASE_INSENSITIVE_ORDER)); return result;
    }
    public static DriverArchive.Installed importDriver(Context context,Uri uri) throws Exception {
        if (!supported(context)) throw new IOException("Custom drivers require the Bionic runtime");
        DriverArchive.Installed result;
        try (InputStream in=context.getContentResolver().openInputStream(uri)) {
            if (in==null) throw new IOException("Cannot open driver ZIP");
            result=DriverArchive.install(root(context),in,Build.VERSION.SDK_INT,file -> {
                JSONObject json=new JSONObject(new String(Files.readAllBytes(file.toPath()),StandardCharsets.UTF_8));
                if (json.getInt("schemaVersion")!=1) throw new IOException("Unsupported driver package schema");
                return new DriverArchive.Metadata(json.getString("name"),json.getString("libraryName"),json.getInt("minApi"));
            });
        }
        select(context,"custom:"+result.id); return result;
    }
    public static String error(Context context,Exception error) {
        int message=R.string.gpu_driver_invalid;
        if (error instanceof DriverArchive.Rejected) {
            DriverArchive.Reason reason=((DriverArchive.Rejected)error).reason;
            if (reason==DriverArchive.Reason.WRONG_ABI) message=R.string.gpu_driver_wrong_abi;
            if (reason==DriverArchive.Reason.NEWER_ANDROID) message=R.string.gpu_driver_newer_android;
        }
        return context.getString(message);
    }
    /** Explicit choices never fall back to a different driver after a load failure. */
    public static void configureEnvironment(Context context,Map<String,String> environment) throws IOException {
        String selection=selected(context);
        environment.remove("GOW3_CUSTOM_VULKAN_DRIVER"); environment.remove("GOW3_VULKAN_DRIVER");
        if (selection.startsWith("custom:")) {
            DriverArchive.Installed driver=DriverArchive.read(root(context),selection.substring(7),Build.VERSION.SDK_INT);
            DriverArchive.validateLibrary(driver.library);
            environment.put("GOW3_BIONIC_DRIVER","custom");
            environment.put("GOW3_CUSTOM_VULKAN_DRIVER",driver.library.getAbsolutePath());
        } else {
            if (!Arrays.asList("auto","gen8","adreno7xx","system").contains(selection)) throw new IOException("Invalid driver selection");
            environment.put("GOW3_BIONIC_DRIVER",selection);
        }
    }
}
