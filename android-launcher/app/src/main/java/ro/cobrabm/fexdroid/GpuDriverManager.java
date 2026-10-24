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
    // PanVK Mali support is experimental, matching ducvd89/Bloodborne-Android.
    private static final String PANVK_ZIP="PanVK-android-v3.2-universal-2a9358a.zip";
    private static final String PANVK_SHA256="68d4eccc1442cb0bef08228c90127388e68bf6087898abc492c717b9a06ca61f";

    public static boolean maliCandidate() {
        if (new File("/dev/kgsl-3d0").exists() || !new File("/dev/mali0").exists()) return false;
        String hardware=Build.HARDWARE==null ? "" : Build.HARDWARE.toLowerCase(Locale.ROOT);
        String soc=Build.VERSION.SDK_INT>=31 && Build.SOC_MANUFACTURER!=null
            ? Build.SOC_MANUFACTURER.toLowerCase(Locale.ROOT) : "";
        return !hardware.equals("qcom") && !soc.contains("qualcomm") && !soc.equals("qti");
    }

    public static String automaticDescription(Context context) {
        if (!maliCandidate()) return "Turnip (Adreno) / system";
        return Build.VERSION.SDK_INT>=35 ? "PanVK 3.2 (Mali; experimental)"
                                       : "System Vulkan (PanVK needs Android 15+)";
    }

    private static DriverArchive.Installed bundledPanvk(Context context) throws Exception {
        if (Build.VERSION.SDK_INT<35 || !maliCandidate())
            throw new IOException("PanVK requires Mali and Android 15+");
        try {
            DriverArchive.Installed cached=DriverArchive.read(root(context),PANVK_SHA256,Build.VERSION.SDK_INT);
            DriverArchive.validateLibrary(cached.library);
            return cached;
        } catch (IOException missingOrDamaged) {
            // Atomic staging in DriverArchive will install the asset below.
            DriverArchive.delete(root(context),PANVK_SHA256);
        }
        try (InputStream in=context.getAssets().open("drivers/"+PANVK_ZIP)) {
            DriverArchive.Installed installed=DriverArchive.install(root(context),in,Build.VERSION.SDK_INT,file -> {
                JSONObject json=new JSONObject(new String(Files.readAllBytes(file.toPath()),StandardCharsets.UTF_8));
                if (json.has("schemaVersion") && json.optInt("schemaVersion")!=1)
                    throw new IOException("Unsupported PanVK driver schema");
                int minApi=Math.max(35,json.optInt("minApi",35));
                return new DriverArchive.Metadata(json.optString("name","PanVK 3.2 Mali"),
                                                  json.getString("libraryName"),minApi);
            });
            if (!PANVK_SHA256.equals(installed.id)) throw new IOException("PanVK zip checksum mismatch");
            return installed;
        }
    }


    public static boolean supported(Context context) { return "com.gow3.android.bionic".equals(context.getPackageName()); }
    private static File root(Context context) { return new File(context.getFilesDir(),"gpu-drivers"); }
    public static String selected(Context context) {
        return context.getSharedPreferences("gow3",Context.MODE_PRIVATE).getString("gpu_driver","auto");
    }
    public static void select(Context context,String value) throws IOException {
        if (!supported(context)) throw new IOException("Custom drivers require the Bionic runtime");
        if (value.startsWith("custom:")) DriverArchive.read(root(context),value.substring(7),Build.VERSION.SDK_INT);
        else if ("panvk".equals(value)) { if (!maliCandidate() || Build.VERSION.SDK_INT<35) throw new IOException("PanVK requires Mali and Android 15+"); }
        else if (!Arrays.asList("auto","gen8","adreno7xx","system").contains(value)) throw new IOException("Invalid driver selection");
        if (!context.getSharedPreferences("gow3",Context.MODE_PRIVATE).edit().putString("gpu_driver",value).commit())
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
        // Automatic Mali selects PanVK only when Android 15+ is available.
        // Manual selections never get silently replaced with a different driver.
        if ("panvk".equals(selection) || ("auto".equals(selection) && maliCandidate())) {
            if (Build.VERSION.SDK_INT>=35) {
                try {
                    DriverArchive.Installed drv=bundledPanvk(context);
                    DriverArchive.validateLibrary(drv.library);
                    environment.put("GOW3_BIONIC_DRIVER","custom");
                    environment.put("GOW3_CUSTOM_VULKAN_DRIVER",drv.library.getAbsolutePath());
                    environment.put("GOW3_GPU_AUTO_REASON","PanVK 3.2 (Mali experimental)");
                    return;
                } catch (Exception ex) {
                    if ("panvk".equals(selection))
                        throw new IOException("Selected PanVK driver failed",ex);
                    android.util.Log.w("GoW3","Automatic PanVK unavailable; use system Vulkan",ex);
                }
            }
            if ("panvk".equals(selection)) throw new IOException("PanVK needs Android 15+");
            environment.put("GOW3_BIONIC_DRIVER","system");
            environment.put("GOW3_GPU_AUTO_REASON","Mali PanVK unavailable; using system Vulkan");
            return;
        }
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
