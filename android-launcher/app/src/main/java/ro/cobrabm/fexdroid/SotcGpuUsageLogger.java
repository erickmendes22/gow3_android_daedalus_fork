package ro.cobrabm.fexdroid;

import android.os.SystemClock;
import android.util.Log;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Locale;

/**
 * SotC-only diagnostic recorder. No render/driver settings are changed.
 * Captures independent sysfs GPU busy and KGSL memstore estimators to the
 * existing LogManager-exported logs/ directory. Opt-in only.
 */
public final class SotcGpuUsageLogger {
    private static final String TAG = "SotC-GPU-Metrics";
    private static Thread worker;
    private static volatile boolean running;

    private SotcGpuUsageLogger() {}

    public static synchronized void start(File logDir) {
        stop();
        if (!logDir.exists() && !logDir.mkdirs()) {
            Log.w(TAG, "Cannot create telemetry log directory: " + logDir);
            return;
        }
        final File file = new File(logDir, "kgsl-gpu-utilization-" + System.currentTimeMillis() + ".csv");
        running = true;
        worker = new Thread(() -> capture(file), "SotC-KGSL-telemetry");
        worker.setDaemon(true);
        worker.start();
    }

    public static synchronized void stop() {
        running = false;
        Thread old = worker;
        worker = null;
        if (old != null) {
            old.interrupt();
            if (old != Thread.currentThread()) {
                try { old.join(1500); }
                catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
            }
        }
    }

    private static void capture(File target) {
        final long startedAt = SystemClock.elapsedRealtime();
        try (BufferedWriter out = new BufferedWriter(new FileWriter(target, false))) {
            out.write("elapsed_ms,wall_ms,sysfs_busy_pct,kgsl_memstore_estimate_pct,gpu_freq_mhz,kgsl_mode,kgsl_status\n");
            out.flush();
            while (running && !Thread.currentThread().isInterrupted()) {
                final long now = SystemClock.elapsedRealtime();
                final String sysfs = sysfsGpuBusy();
                final Integer kgsl = KgslLoadFallback.busyPercent();
                final String freq = gpuClockMHz();
                final String mode = KgslBusy.INSTANCE.getStatus();
                final String status = kgsl == null ? "unavailable" : "estimated";
                out.write((now - startedAt) + "," + System.currentTimeMillis() + "," +
                          sysfs + "," + (kgsl == null ? "N/A" : kgsl.toString()) + "," +
                          freq + "," + csv(mode) + "," + status + "\n");
                out.flush();
                try { Thread.sleep(2000); }
                catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
            }
        } catch (Exception ex) {
            Log.w(TAG, "KGSL diagnostic logging failed: " + ex);
        } finally {
            KgslLoadFallback.stop();
        }
    }

    private static String csv(String s) {
        return "\"" + (s == null ? "" : s.replace("\"", "\"\"").replace("\r", " ").replace("\n", " ")) + "\"";
    }

    private static String readFirstLine(String path) {
        try {
            File f = new File(path);
            if (!f.isFile()) return null;
            try (java.io.BufferedReader in = new java.io.BufferedReader(new java.io.FileReader(f))) {
                return in.readLine();
            }
        } catch (Exception ignored) { return null; }
    }

    /** KGSL gpubusy contains accumulated active and total microseconds. */
    private static String sysfsGpuBusy() {
        String raw = readFirstLine("/sys/class/kgsl/kgsl-3d0/gpubusy");
        if (raw != null) {
            try {
                String[] values = raw.trim().split("\\s+");
                if (values.length >= 2) {
                    long busy = Long.parseLong(values[0]);
                    long total = Long.parseLong(values[1]);
                    if (total > 0 && busy >= 0 && busy <= total) {
                        return String.format(Locale.US, "%.1f", 100.0 * busy / total);
                    }
                }
            } catch (Exception ignored) {}
        }
        for (String path : new String[] {
                "/sys/class/kgsl/kgsl-3d0/devfreq/gpu_load",
                "/sys/class/kgsl/kgsl-3d0/gpu_load"}) {
            raw = readFirstLine(path);
            if (raw == null) continue;
            try {
                double n = Double.parseDouble(raw.trim().replace("%", ""));
                if (n >= 0 && n <= 100) return String.format(Locale.US, "%.1f", n);
            } catch (Exception ignored) {}
        }
        return "N/A";
    }

    private static String gpuClockMHz() {
        for (String path : new String[] {
                "/sys/class/kgsl/kgsl-3d0/devfreq/cur_freq",
                "/sys/class/kgsl/kgsl-3d0/gpuclk"}) {
            String raw = readFirstLine(path);
            if (raw == null) continue;
            try {
                long hz = Long.parseLong(raw.trim());
                double mhz = hz >= 100_000_000L ? hz / 1_000_000.0 :
                             hz >= 100_000L ? hz / 1000.0 : hz;
                if (mhz > 0 && mhz < 5000)
                    return String.format(Locale.US, "%.1f", mhz);
            } catch (Exception ignored) {}
        }
        return "N/A";
    }
}
