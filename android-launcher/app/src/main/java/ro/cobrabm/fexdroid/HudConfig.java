package ro.cobrabm.fexdroid;

import android.content.Context;
import android.content.SharedPreferences;
import java.io.*;
import java.util.*;
import java.nio.charset.StandardCharsets;

/** One shared HUD configuration for launcher, native in-game menu and Android HUD.
 * Source of truth: gow3port/gow3.ini (also written by Gow3Settings::Save).
 */
final class HudConfig {
    static final String ENABLED = "show_fps";
    static final String ANCHOR = "overlay_corner"; // horizontal: 0 left, 4 center, 1 right
    static final String VERTICAL = "overlay_anchor_y"; // 0 top, 1 center, 2 bottom
    static final String DX = "overlay_offset_x";  // dp: -300..300
    static final String DY = "overlay_offset_y";  // dp: 0..300

    final boolean enabled;
    final int anchor, vertical, dx, dy;

    HudConfig(boolean enabled, int anchor, int vertical, int dx, int dy) {
        this.enabled = enabled;
        this.anchor = anchor == 0 || anchor == 4 ? anchor : 1;
        this.vertical = Math.max(0, Math.min(2, vertical));
        this.dx = Math.max(-300, Math.min(300, dx));
        this.dy = Math.max(0, Math.min(300, dy));
    }
    static int number(String s, int fallback) {
        try { return Integer.parseInt(s.trim()); } catch (Exception ignored) { return fallback; }
    }
    static Map<String,String> readValues(File file) {
        Map<String,String> values = new LinkedHashMap<>();
        if (!file.isFile()) return values;
        try (BufferedReader r = new BufferedReader(new InputStreamReader(
                new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) {
                int equals = line.indexOf('=');
                if (equals > 0 && !line.trim().startsWith("#")) {
                    values.put(line.substring(0, equals).trim(), line.substring(equals + 1).trim());
                }
            }
        } catch (IOException ex) {
            android.util.Log.w("God of War III", "HUD read: " + ex);
        }
        return values;
    }
    static HudConfig load(File file) {
        Map<String,String> m = readValues(file);
        return new HudConfig("1".equals(m.get(ENABLED)),
                number(m.get(ANCHOR), 1), number(m.get(VERTICAL), 0), 0, 0);
    }
    static synchronized boolean update(File file, Map<String,String> changes) {
        ArrayList<String> original = new ArrayList<>();
        if (file.isFile()) {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    new FileInputStream(file), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) original.add(line);
            } catch (IOException ex) { return false; }
        }
        Map<String,String> pending = new LinkedHashMap<>(changes);
        ArrayList<String> lines = new ArrayList<>();
        for (String line : original) {
            int equals = line.indexOf('=');
            String key = equals > 0 && !line.trim().startsWith("#")
                    ? line.substring(0, equals).trim() : "";
            if (pending.containsKey(key)) {
                lines.add(key + "=" + pending.remove(key));
            } else {
                lines.add(line);
            }
        }
        for (Map.Entry<String,String> e : pending.entrySet()) {
            lines.add(e.getKey() + "=" + e.getValue());
        }
        File temp = new File(file.getPath() + ".hud-tmp");
        try (FileOutputStream stream = new FileOutputStream(temp);
             OutputStreamWriter writer = new OutputStreamWriter(stream, StandardCharsets.UTF_8)) {
            for (String line : lines) { writer.write(line); writer.write('\n'); }
            writer.flush();
            stream.getFD().sync();
        } catch (IOException ex) {
            android.util.Log.e("God of War III", "HUD write: " + ex);
            temp.delete();
            return false;
        }
        if (!temp.renameTo(file)) {
            android.util.Log.e("God of War III", "HUD update rename failed");
            temp.delete();
            return false;
        }
        return true;
    }
    static void migrateLegacy(Context context, File ini) {
        SharedPreferences prefs = context.getSharedPreferences("gow3", Context.MODE_PRIVATE);
        if (prefs.getBoolean("unified_perf_hud_migrated", false)) return;
        Map<String,String> old = readValues(ini);
        if (prefs.getBoolean("performance_hud", false) && !"1".equals(old.get(ENABLED))) {
            Map<String,String> changes = new LinkedHashMap<>();
            changes.put(ENABLED, "1");
            if (!update(ini, changes)) return; // Retry migration rather than lose enabled state.
        }
        prefs.edit().putBoolean("unified_perf_hud_migrated", true).apply();
    }
    private HudConfig() { this(false, 1, 0, 0, 0); }
}
