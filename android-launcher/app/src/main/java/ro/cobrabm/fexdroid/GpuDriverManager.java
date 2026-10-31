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
    // Newer Mesa/PanVK driver is explicitly selectable for Mali A/B comparison.
    // Do not change the automatic driver or any Adreno/Exynos selections.
    private static final String PANVK_NEXT_ZIP="Mesa-PanVK-Android-v26.3.1-795ca7ff.adpkg.zip";
    private static final String PANVK_NEXT_SHA256="0c61ef0cdd5c9314715c4a0cc34a5929dbd727ce7a30545b947577e83600b900";

    // PanVK CSF is NOT compatible with every Mali. Reject older
    // Job-Manager Mali (G52/G57/G76/G77/G78) and unknown GPU variants.
    // Query the actual GLES renderer via a temporary pbuffer so the Android
    // launcher never guesses GPU generation from the phone manufacturer.
    private static String maliRenderer() {
        android.opengl.EGLDisplay d=android.opengl.EGL14.eglGetDisplay(android.opengl.EGL14.EGL_DEFAULT_DISPLAY);
        if (d==android.opengl.EGL14.EGL_NO_DISPLAY) return "";
        int[] version=new int[2];
        if (!android.opengl.EGL14.eglInitialize(d,version,0,version,1)) return "";
        android.opengl.EGLContext ctx=android.opengl.EGL14.EGL_NO_CONTEXT;
        android.opengl.EGLSurface surface=android.opengl.EGL14.EGL_NO_SURFACE;
        try {
            int[] configAttrs={android.opengl.EGL14.EGL_RENDERABLE_TYPE,
                android.opengl.EGL14.EGL_OPENGL_ES2_BIT,
                android.opengl.EGL14.EGL_SURFACE_TYPE,android.opengl.EGL14.EGL_PBUFFER_BIT,
                android.opengl.EGL14.EGL_NONE};
            android.opengl.EGLConfig[] configs=new android.opengl.EGLConfig[1];
            int[] count=new int[1];
            if (!android.opengl.EGL14.eglChooseConfig(d,configAttrs,0,configs,0,1,count,0) ||
                count[0]<1 || configs[0]==null) return "";
            int[] ctxAttrs={android.opengl.EGL14.EGL_CONTEXT_CLIENT_VERSION,2,
                            android.opengl.EGL14.EGL_NONE};
            ctx=android.opengl.EGL14.eglCreateContext(d,configs[0],
                android.opengl.EGL14.EGL_NO_CONTEXT,ctxAttrs,0);
            int[] surfaceAttrs={android.opengl.EGL14.EGL_WIDTH,1,
                                android.opengl.EGL14.EGL_HEIGHT,1,android.opengl.EGL14.EGL_NONE};
            surface=android.opengl.EGL14.eglCreatePbufferSurface(d,configs[0],surfaceAttrs,0);
            if (ctx==android.opengl.EGL14.EGL_NO_CONTEXT ||
                surface==android.opengl.EGL14.EGL_NO_SURFACE ||
                !android.opengl.EGL14.eglMakeCurrent(d,surface,surface,ctx)) return "";
            String name=android.opengl.GLES20.glGetString(android.opengl.GLES20.GL_RENDERER);
            return name==null ? "" : name;
        } catch (RuntimeException ex) {
            return "";
        } finally {
            android.opengl.EGL14.eglMakeCurrent(d,android.opengl.EGL14.EGL_NO_SURFACE,
                android.opengl.EGL14.EGL_NO_SURFACE,android.opengl.EGL14.EGL_NO_CONTEXT);
            if (surface!=android.opengl.EGL14.EGL_NO_SURFACE) android.opengl.EGL14.eglDestroySurface(d,surface);
            if (ctx!=android.opengl.EGL14.EGL_NO_CONTEXT) android.opengl.EGL14.eglDestroyContext(d,ctx);
            android.opengl.EGL14.eglTerminate(d);
        }
    }
    static boolean supportedCsfMali(String renderer) {
        if (renderer==null) return false;
        return java.util.regex.Pattern.compile(
            "(?i).*\\b(?:Mali|Immortalis)[- ]G(?:610|615|620|710|715|720|725|730)(?:\\b|[^0-9].*)")
            .matcher(renderer).matches();
    }
    public static boolean exynosDevice() {
        String hardware=Build.HARDWARE==null ? "" : Build.HARDWARE.toLowerCase(Locale.ROOT);
        String soc=Build.VERSION.SDK_INT>=31 && Build.SOC_MANUFACTURER!=null
            ? Build.SOC_MANUFACTURER.toLowerCase(Locale.ROOT) : "";
        return hardware.contains("exynos") || hardware.startsWith("s5e") || soc.contains("samsung");
    }
    public static boolean adrenoCandidate() {
        if (exynosDevice()) return false;
        String hardware=Build.HARDWARE==null ? "" : Build.HARDWARE.toLowerCase(Locale.ROOT);
        String soc=Build.VERSION.SDK_INT>=31 && Build.SOC_MANUFACTURER!=null
            ? Build.SOC_MANUFACTURER.toLowerCase(Locale.ROOT) : "";
        return new File("/dev/kgsl-3d0").exists() || hardware.equals("qcom") ||
               soc.contains("qualcomm") || soc.equals("qti");
    }
    static boolean supportedPanvkDevice(int api,String hardware,String soc,
                                        boolean kgsl,boolean mali,String renderer) {
        hardware=hardware==null ? "" : hardware.toLowerCase(Locale.ROOT);
        soc=soc==null ? "" : soc.toLowerCase(Locale.ROOT);
        return api>=35 && mali && !kgsl && !hardware.contains("exynos") &&
            !hardware.startsWith("s5e") && !soc.contains("samsung") &&
            !hardware.equals("qcom") && !soc.contains("qualcomm") && !soc.equals("qti") &&
            supportedCsfMali(renderer);
    }
    public static boolean maliCandidate() {
        boolean kgsl=new File("/dev/kgsl-3d0").exists();
        boolean mali=new File("/dev/mali0").exists();
        if (exynosDevice() || Build.VERSION.SDK_INT<35 || kgsl || !mali) return false;
        return supportedPanvkDevice(Build.VERSION.SDK_INT,Build.HARDWARE,
            Build.VERSION.SDK_INT>=31 ? Build.SOC_MANUFACTURER : "",kgsl,mali,maliRenderer());
    }

    private static boolean nextPanvkVerifiedAutoDevice() {
        // The 26.3.1 release contains actual G615 MC6 validation, not G720
        // gameplay validation. Keep G720 on the established driver by default.
        String renderer=maliRenderer();
        return supportedCsfMali(renderer) &&
               renderer.toLowerCase(Locale.ROOT).contains("g615");
    }
    public static String automaticDescription(Context context) {
        if (maliCandidate()) return context.getString(nextPanvkVerifiedAutoDevice()
            ? R.string.gpu_driver_panvk_next : R.string.gpu_driver_panvk);
        if (adrenoCandidate()) return context.getString(R.string.gpu_driver_adreno_auto);
        return context.getString(R.string.gpu_driver_system);
    }

    private static DriverArchive.Installed bundledPanvk(Context context, boolean next) throws Exception {
        if (Build.VERSION.SDK_INT<35 || !maliCandidate())
            throw new IOException("PanVK requires Mali and Android 15+");
        final String driverSha=next ? PANVK_NEXT_SHA256 : PANVK_SHA256;
        final String driverZip=next ? PANVK_NEXT_ZIP : PANVK_ZIP;
        try {
            DriverArchive.Installed cached=DriverArchive.read(root(context),driverSha,Build.VERSION.SDK_INT);
            DriverArchive.validateLibrary(cached.library);
            return cached;
        } catch (IOException missingOrDamaged) {
            // Atomic staging in DriverArchive will install the asset below.
            DriverArchive.delete(root(context),driverSha);
        }
        try (InputStream in=context.getAssets().open("drivers/"+driverZip)) {
            DriverArchive.Installed installed=DriverArchive.install(root(context),in,Build.VERSION.SDK_INT,file -> {
                JSONObject json=new JSONObject(new String(Files.readAllBytes(file.toPath()),StandardCharsets.UTF_8));
                if (json.has("schemaVersion") && json.optInt("schemaVersion")!=1)
                    throw new IOException("Unsupported PanVK driver schema");
                int minApi=Math.max(35,json.optInt("minApi",35));
                return new DriverArchive.Metadata(json.optString("name",next ? "PanVK 26.3.1 Mali" : "PanVK 3.2 Mali"),
                                                  json.getString("libraryName"),minApi);
            });
            if (!driverSha.equals(installed.id)) throw new IOException("PanVK zip checksum mismatch");
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
        else if ("panvk".equals(value) || "panvk-next".equals(value)) { if (!maliCandidate() || Build.VERSION.SDK_INT<35) throw new IOException("PanVK requires Mali and Android 15+"); }
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
                // PanVK and most standard adrenotools ZIPs omit the fork's
                // private schemaVersion. Keep rejecting unknown explicit schemas.
                if (json.has("schemaVersion") && json.optInt("schemaVersion")!=1)
                    throw new IOException("Unsupported driver package schema");
                return new DriverArchive.Metadata(json.optString("name","Android Vulkan driver"),
                                                  json.getString("libraryName"),json.optInt("minApi",28));
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
        String selection=exynosDevice() ? "system" : selected(context);
        environment.remove("GOW3_CUSTOM_VULKAN_DRIVER"); environment.remove("GOW3_VULKAN_DRIVER");
        // Automatic Mali selects PanVK only when Android 15+ is available.
        // Manual selections never get silently replaced with a different driver.
        if ("panvk".equals(selection) || "panvk-next".equals(selection) ||
            ("auto".equals(selection) && maliCandidate())) {
            if (Build.VERSION.SDK_INT>=35) {
                try {
                    final boolean wantNext = "panvk-next".equals(selection) ||
                        ("auto".equals(selection) && nextPanvkVerifiedAutoDevice());
                    DriverArchive.Installed drv;
                    boolean usingNext = wantNext;
                    try {
                        drv = bundledPanvk(context, wantNext);
                    } catch (Exception nextFailed) {
                        if (!"auto".equals(selection) || !wantNext) throw new IOException("Selected PanVK driver unavailable",nextFailed);
                        // A failed auto-update must not leave a supported Mali
                        // device on the stock Vulkan loader. Use the old, pinned
                        // PanVK instead; explicit driver selection never falls back.
                        android.util.Log.w("GoW3","PanVK 26.3.1 auto unavailable; using 3.2",nextFailed);
                        drv = bundledPanvk(context, false);
                        usingNext = false;
                    }
                    DriverArchive.validateLibrary(drv.library);
                    environment.put("GOW3_BIONIC_DRIVER","custom");
                    environment.put("GOW3_CUSTOM_VULKAN_DRIVER",drv.library.getAbsolutePath());
                    environment.put("GOW3_GPU_AUTO_REASON",
                        usingNext ? "PanVK 26.3.1 (Mali G615 tested release)"
                                  : "PanVK 3.2 (Mali experimental)");
                    return;
                } catch (Exception ex) {
                    if ("panvk".equals(selection) || "panvk-next".equals(selection))
                        throw new IOException("Selected PanVK driver failed",ex);
                    android.util.Log.w("GoW3","Automatic PanVK unavailable; use system Vulkan",ex);
                }
            }
            if ("panvk".equals(selection) || "panvk-next".equals(selection))
                throw new IOException("PanVK needs Android 15+");
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
            // Old preferences must never force an Adreno HAL onto Exynos/Mali.
            if (("auto".equals(selection) && !adrenoCandidate()) ||
                (("gen8".equals(selection) || "adreno7xx".equals(selection)) && !adrenoCandidate()))
                selection="system";
            environment.put("GOW3_BIONIC_DRIVER",selection);
        }
    }
}
