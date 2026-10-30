package ro.cobrabm.fexdroid;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Typeface;
import android.view.View;
import android.widget.CompoundButton;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Switch;
import android.widget.TextView;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.BufferedReader;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Graphics settings for the Thor, kept in gow3.ini (run-gow3.sh reads them at start: scene
 *  size, game resolution, the game's effect patches). Other lines and comments of the file are kept. */
final class SettingsDialog {
    /** Scene sizes of the presets at the Thor's 1280x720 output (run-gow3.sh). */
    private static final String[] PRESETS={"Native (1280×720)","Quality (854×480)",
        "Performance (640×360)","Ultra Performance (426×240)"};
    private static final String[] PRESET_VALUES={"0","1","3","4"};
    private static final String[][] EFFECTS={
        {"effect_chromatic_aberration","Chromatic aberration","1"},
        {"effect_dof","Depth of field","1"},
        {"effect_motion_blur","Motion blur","1"},
        {"effect_ssao","Ambient occlusion (SSAO)","1"},
        {"effect_game_aa","Game's own anti-aliasing","1"},
        {"effect_dynamic_shadows","Shadows from dynamic lights","1"},
        {"effect_ssr","Screen-space reflections (not in the original)","0"},
    };
    // Legacy temporal reconstruction controls are not exposed on Android.
    /** Game settings: the game patches run-gow3.sh applies at start (patch-parts), as upstream's
     *  System menu pages and launcher offer them: {key, title, note, default}. */
    private static final String[][] GAME_PATCHES={
        {"skip_network_choice","Skip the online/offline screen","Start straight at the main menu, offline (there is no PSN here)","1"},
        {"skip_intro","Skip startup intros","The logos and intro movie at start","0"},
        {"debug_camera","Free camera","Toggle it with Cross + L3","0"},
        {"debug_menu","Debug menu","The game's own debug menu; needs its font files","0"},
    };
    /** Cheats: code hooks of the game applied at start (build_gow3_patch_parts.py, run-gow3.sh).
     *  key MUST match the runtime's cheat_keys (gow3_settings.cpp): cheat_item is the singular one. */
    private static final String[][] CHEATS={
        {"cheat_health","Infinite health","Your HP refills to full every frame","0"},
        {"cheat_item","Infinite blood vials and items","Using a blood vial, bullet or other item leaves its count as it was "
            +"(items moved to storage or given away stay too)","0"},
    };
    // One selector for all original and newly verified in-game resolutions.
    // The PS4 original uses the "native" storage key but appears as 1080p.
    private static final String[] RESOLUTION_VALUES={"240p","360p","424p","480p",
        "540p","720p","900p","native","1440p","1800p","4K"};
    private static final String[] RESOLUTION_NAMES={"240p","360p","424p","480p",
        "540p","720p","900p","1080p","1440p","1800p","4K"};
    // FPS 上限只给运行时 FPS_LIMITS 的取值（gow3_graphics.h 的 FpsLimits：30/60/120/240/0）。
    // 原来还提供 40/45，但 ParseFpsLimit 把不在表里的值一律映射成 0（不限制），等于"看着限帧、
    // 实际无限"，因此删除；取值域与 my-docs/gow3/LAUNCHER.md §3.2 及 Home 页 LaunchParams.kt 对齐。
    private static final String[] FPS_VALUES={"30","60","120","240","0"};
    private static final String[] FPS_NAMES={"30 (the game's own)","60","120","240","Unlimited"};
    /** Snapdragon 8 Gen 2: three Cortex-A510, four Cortex-A715, one Cortex-X3. */
    private static final String[] CORE_NAMES={"Core 0 · efficiency A510 2.0 GHz","Core 1 · efficiency A510 2.0 GHz",
        "Core 2 · efficiency A510 2.0 GHz","Core 3 · performance A715 2.8 GHz","Core 4 · performance A715 2.8 GHz",
        "Core 5 · performance A715 2.8 GHz","Core 6 · performance A715 2.8 GHz","Core 7 · prime X3 3.2 GHz"};
    private static final String[] LOD_VALUES={"-2","0","1","2"};
    private static final String[] LOD_NAMES={"Highest","Game default","Lower","Lowest"};

    private final Activity activity;
    private final File file;
    private final Runnable restart;
    private final Map<String,String> values=new LinkedHashMap<>();
    private final List<String> lines=new ArrayList<>();

    SettingsDialog(Activity activity,File file,Runnable restart) {
        this.activity=activity; this.file=file; this.restart=restart;
    }

    private int dp(float n) { return Math.round(n*activity.getResources().getDisplayMetrics().density); }
    private String get(String key,String fallback) { String v=values.get(key); return v==null || v.isEmpty() ? fallback : v; }

    private void load() {
        values.clear(); lines.clear();
        if (!file.isFile()) return;
        try (BufferedReader r=new BufferedReader(new InputStreamReader(new FileInputStream(file),"UTF-8"))) {
            for (String line; (line=r.readLine())!=null;) {
                lines.add(line);
                int eq=line.indexOf('=');
                if (eq>0 && !line.startsWith("#")) values.put(line.substring(0,eq).trim(),line.substring(eq+1).trim());
            }
        } catch (Exception ex) { android.util.Log.e("God of War III","settings: "+ex); }
    }
    /** Changed keys replace their lines; new keys are appended. Written whole, then renamed. */
    private boolean save(Map<String,String> changed) {
        List<String> out=new ArrayList<>();
        Map<String,String> pending=new LinkedHashMap<>(changed);
        for (String line:lines) {
            int eq=line.indexOf('=');
            String key=eq>0 && !line.startsWith("#") ? line.substring(0,eq).trim() : null;
            if (key!=null && pending.containsKey(key)) out.add(key+"="+pending.remove(key));
            else out.add(line);
        }
        for (Map.Entry<String,String> e:pending.entrySet()) out.add(e.getKey()+"="+e.getValue());
        File temporary=new File(file.getPath()+".tmp");
        try (Writer w=new OutputStreamWriter(new FileOutputStream(temporary),"UTF-8")) {
            for (String line:out) w.write(line+"\n");
        } catch (Exception ex) { android.util.Log.e("God of War III","settings: "+ex); return false; }
        return temporary.renameTo(file);
    }

    private TextView heading(LinearLayout box,String title) {
        TextView t=new TextView(activity); t.setText(UiText.get(activity, title)); t.setTextSize(15);
        t.setTypeface(Typeface.DEFAULT,Typeface.BOLD); t.setPadding(0,dp(14),0,dp(4));
        box.addView(t); return t;
    }
    private Switch toggle(LinearLayout box,String title,boolean on) {
        Switch s=new Switch(activity); s.setText(UiText.get(activity, title)); s.setChecked(on); s.setTextSize(15);
        s.setPadding(0,dp(6),0,dp(6)); box.addView(s); return s;
    }
    private RadioGroup choices(LinearLayout box,String[] names,int selected) {
        RadioGroup g=new RadioGroup(activity);
        for (int i=0;i<names.length;++i) {
            RadioButton b=new RadioButton(activity); b.setId(View.generateViewId()); b.setText(UiText.get(activity, names[i])); b.setTextSize(15);
            g.addView(b); if (i==selected) g.check(b.getId());
        }
        box.addView(g); return g;
    }
    private static int indexOf(String[] values,String value,int fallback) {
        for (int i=0;i<values.length;++i) if (values[i].equals(value)) return i;
        return fallback;
    }
    /** A taskset list ("0-2,5", "3-7"); empty: every core. */
    private static boolean[] parseCpus(String list,int count) {
        boolean[] on=new boolean[count];
        if (list.trim().isEmpty()) { java.util.Arrays.fill(on,true); return on; }
        for (String part:list.split(",")) {
            try {
                String[] range=part.trim().split("-");
                int from=Integer.parseInt(range[0].trim()), to=range.length>1 ? Integer.parseInt(range[1].trim()) : from;
                for (int i=Math.max(0,from);i<=Math.min(count-1,to);++i) on[i]=true;
            } catch (NumberFormatException ignored) {}
        }
        boolean any=false; for (boolean b:on) any|=b;
        if (!any) java.util.Arrays.fill(on,true);
        return on;
    }
    private static String cpuList(Switch[] cores) {
        StringBuilder list=new StringBuilder(); boolean all=true;
        for (int i=0;i<cores.length;++i) {
            if (!cores[i].isChecked()) { all=false; continue; }
            if (list.length()>0) list.append(',');
            list.append(i);
        }
        return all ? "" : list.toString();
    }
    private static String canonicalResolution(String value) {
        switch (value) {
            case "426x240": return "240p";
            case "640x360": return "360p";
            case "752x424": return "424p";
            case "854x480": return "480p";
            case "960x540": return "540p";
            case "1280x720": return "720p";
            case "800p": case "1600x900": return "900p";
            case "1080p": return "native";
            default: return value;
        }
    }
    private static int checkedIndex(RadioGroup g) {
        for (int i=0;i<g.getChildCount();++i) if (((RadioButton)g.getChildAt(i)).isChecked()) return i;
        return -1;
    }

    void show() {
        load();
        LinearLayout box=new LinearLayout(activity); box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(24),dp(4),dp(24),dp(8));

        heading(box,"Render resolution");
        final RadioGroup resolutions=choices(box,RESOLUTION_NAMES,
            indexOf(RESOLUTION_VALUES,canonicalResolution(get("render_resolution","720p")),5));
        final TextView nativeNote=new TextView(activity);
        nativeNote.setText(UiText.get(activity, "Choose the game rendering resolution. Changes apply after restart."));
        nativeNote.setTextSize(13); nativeNote.setAlpha(0.7f); box.addView(nativeNote);
        final Switch expandArena=toggle(box,"Texture corruption fix","1".equals(get("expand_video_arena","1")));
        final Switch startupFix=toggle(box,"Startup black screen fix","1".equals(get("patch_startup_black_screen","1")));
        TextView arenaNote=new TextView(activity); arenaNote.setTextSize(13); arenaNote.setAlpha(0.7f);
        arenaNote.setText(UiText.get(activity, "OFF keeps the original arena. Texture errors or crashes may occur, especially at higher resolutions. Requires restart."));
        box.addView(arenaNote);
        heading(box,"Anisotropic filtering");
        final String[] anisotropyValues={"0","2","4","8","16"};
        final RadioGroup anisotropy=choices(box,new String[]{"Game default","2×","4×","8×","16×"},
            indexOf(anisotropyValues,get("anisotropy","0"),0));
        heading(box,"Image");
        // Temporary spatial-only mode: explicitly available independent of
        // the selected game resolution, including native and 8K. No temporal
        // reconstruction, history, jitter or automatic 720p resolution patch.
        final Switch gsr2Spatial=toggle(box,"GSR2 spatial filter (no temporal)",
            "gsr2".equals(get("upscaler","off")));
        final TextView gsr2Note=new TextView(activity);
        gsr2Note.setText(UiText.get(activity,
            "Current-frame Qualcomm filter only. No temporal accumulation. " +
            "Uses the game resolution selected above; requires restart. " +
            "Very high resolutions can use significantly more GPU memory."));
        gsr2Note.setTextSize(13); gsr2Note.setAlpha(0.7f); box.addView(gsr2Note);
        final Switch sharpen=toggle(box,"Sharpening","1".equals(get("sharpen","0")));
        final TextView sharpLabel=new TextView(activity); sharpLabel.setTextSize(14); box.addView(sharpLabel);
        final SeekBar sharpness=new SeekBar(activity); sharpness.setMax(100);
        float initial=0.5f;
        try { initial=Float.parseFloat(get("sharpness","0.5")); } catch (NumberFormatException ignored) {}
        sharpness.setProgress(Math.round(Math.max(0,Math.min(1,initial))*100));
        SeekBar.OnSeekBarChangeListener sharpText=new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s,int p,boolean user) { sharpLabel.setText(UiText.get(activity, "Sharpness: "+p+"%")); }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {}
        };
        sharpness.setOnSeekBarChangeListener(sharpText); sharpText.onProgressChanged(sharpness,sharpness.getProgress(),false);
        box.addView(sharpness);
        sharpen.setOnCheckedChangeListener((b,on) -> sharpness.setEnabled(on)); sharpness.setEnabled(sharpen.isChecked());
        // One shared HUD replaces the retired in-game FPS overlay; uses the same
        // gow3.ini keys as native Overlay tab and the Android drawer (live, no restart).
        final HudControls hud = new HudControls(activity, file, box, HudConfig.load(file));
        // effect_dynamic_shadows is consumed by launch_env.py to select the
        // SHA-gated Disable Dynamic Shadows eboot patch on the next launch.
        heading(box,"Game effects");
        final Switch disableShadows=toggle(box,"Disable dynamic shadows",
            "1".equals(get("disable_dynamic_shadows",
                           "0".equals(get("effect_dynamic_shadows","1")) ? "1" : "0")));

        // FPS 上限入口：取值域必须与运行时 FPS_LIMITS（gow3_graphics.h 的 FpsLimits：30/60/120/
        // 240/0）完全一致——ParseFpsLimit 把表外的值（例如旧版提供的 40/45）一律当成 0（不限制），
        // 给出这类选项等于"看着限帧、实际无限"，所以已删除。另外 120/240 还依赖引擎帧率补丁
        // （gow3.ini 的 engine_fps），本弹窗不写 engine_fps，实际帧率仍受 PresentLimit 的引擎
        // 速率约束；Home 页 LaunchParams.kt 的 fps_limit 同此。
        heading(box,"FPS limit");
        final RadioGroup fpsLimit=choices(box,FPS_NAMES,indexOf(FPS_VALUES,get("fps_limit","30"),0));
        TextView fpsNote=new TextView(activity); fpsNote.setTextSize(13); fpsNote.setAlpha(0.7f);
        fpsNote.setText(UiText.get(activity, "Above 30 uses the community frame-rate patch (game timing follows the real frame time)."));
        box.addView(fpsNote);

        /* 以下三段已注释掉：写入 gow3.ini 的键在本仓库的 fexdroid 启动链路里没有消费方，勾选后
         * 游戏不会有任何变化，对玩家是误导，等接通再放开（不要直接删，接通时整段取消注释即可）。
         *
         * CPU 核心 → thor_cpus（taskset 列表格式）：run-gow3.sh → patches.py --extra / launch_env.py
         * → probe 都不读它，也没有对应的 GOW3_* 环境变量；消费 taskset 的是桌面端 tools/restart.sh
         * 的 $CPUS。
        heading(box,"CPU cores the game may use");
        final Switch[] cores=new Switch[CORE_NAMES.length];
        boolean[] allowed=parseCpus(get("thor_cpus",""),CORE_NAMES.length);
        for (int i=0;i<cores.length;++i) cores[i]=toggle(box,CORE_NAMES[i],allowed[i]);
        CompoundButton.OnCheckedChangeListener keepOne=(b,on) -> {
            if (on) return;
            for (Switch c:cores) if (c.isChecked()) return;
            b.setChecked(true); // at least one core
        };
        for (Switch c:cores) c.setOnCheckedChangeListener(keepOne);
         *
         * 特效 → effect_*、模型细节 → model_lod：启动链路选补丁是按补丁名经 patches.py --extra /
         * patches.json（run.sh、run-gow3.sh），既不读这些 ini 键，gow3_settings.cpp 也不解析；
         * my-docs/gow3/LAUNCHER.md §3.2 的 GOW3 launcher 键表同样不含它们（只在 Bloodborne 参考
         * 配置 bbport-ini.md 出现）。预编译它们的 Thor 路径 build_gow3_patch_parts.py 不被
         * run-gow3.sh 使用。
        heading(box,"Game effects");
        final Switch[] effects=new Switch[EFFECTS.length];
        for (int i=0;i<EFFECTS.length;++i) effects[i]=toggle(box,EFFECTS[i][1],"1".equals(get(EFFECTS[i][0],EFFECTS[i][2])));

        heading(box,"Model detail");
        int lod=1;
        for (int i=0;i<LOD_VALUES.length;++i) if (LOD_VALUES[i].equals(get("model_lod","0")) lod=i;
        final RadioGroup lods=choices(box,LOD_NAMES,lod);
         */

        ScrollView scroll=new ScrollView(activity); scroll.addView(box);
        new AlertDialog.Builder(activity).setTitle(UiText.get(activity, "Graphics settings")).setView(scroll)
            .setNegativeButton(UiText.get(activity, "Cancel"),null)
            .setPositiveButton(UiText.get(activity, "Apply & restart"),(d,w) -> {
                Map<String,String> changed=new LinkedHashMap<>();
                changed.put("expand_video_arena",expandArena.isChecked() ? "1" : "0");
                changed.put("patch_startup_black_screen",startupFix.isChecked() ? "1" : "0");
                changed.put("anisotropy",anisotropyValues[Math.max(0,checkedIndex(anisotropy))]);
                changed.put("fps_limit",FPS_VALUES[Math.max(0,checkedIndex(fpsLimit))]);
                changed.put("render_resolution",RESOLUTION_VALUES[Math.max(0,checkedIndex(resolutions))]);
                changed.put("disable_dynamic_shadows",disableShadows.isChecked() ? "1" : "0");
                changed.put("effect_dynamic_shadows",disableShadows.isChecked() ? "0" : "1");
                changed.put("upscaler",gsr2Spatial.isChecked() ? "gsr2" : "off");
                changed.put("sharpen",sharpen.isChecked() ? "1" : "0");
                changed.put("sharpness",String.format(Locale.ROOT,"%.2f",sharpness.getProgress()/100f));
                changed.putAll(hud.values());
                // thor_cpus / effect_* / model_lod 随上面三段一起注释掉了，这里也不写。
                apply(changed);
            }).show();
    }

    /** Saves the changed keys and restarts the game when any differs from the file. */
    private void apply(Map<String,String> changed) {
        boolean same=true;
        for (Map.Entry<String,String> e:changed.entrySet()) if (!e.getValue().equals(values.get(e.getKey()))) same=false;
        if (same) return;
        // Pure HUD edits take effect immediately through GameActivity's native INI watcher.
        // Only game graphics changes should restart the emulator and risk unsaved progress.
        boolean gameRestartNeeded = false;
        for (Map.Entry<String,String> entry : changed.entrySet()) {
            String key = entry.getKey();
            if (!entry.getValue().equals(values.get(key)) &&
                    !key.equals(HudConfig.ENABLED) && !key.equals(HudConfig.ANCHOR) &&
                    !key.equals(HudConfig.VERTICAL) && !key.equals(HudConfig.DX) && !key.equals(HudConfig.DY)) {
                gameRestartNeeded = true;
            }
        }
        if (save(changed)) { if (gameRestartNeeded) restart.run(); }
        else new AlertDialog.Builder(activity).setMessage(UiText.get(activity, "The settings could not be saved.")).setPositiveButton(UiText.get(activity, "OK"),null).show();
    }

    /* showGame() 已注释掉（入口也随之在 GameActivity 里隐藏）：这四个 ini 键
     * （skip_network_choice / skip_intro / debug_camera / debug_menu）在本仓库的启动链路里没有
     * 消费方——run-gow3.sh 与 run.sh 都是按补丁名经 patches.py --extra / patches.json 选补丁，
     * gow3_settings.cpp 也不解析它们；预编译它们的 Thor 路径 build_gow3_patch_parts.py 不被
     * run-gow3.sh 使用。开关写进 gow3.ini 后游戏不会有任何变化，属于误导入口。
     * 等启动链路把这些键翻译成补丁名（或接入 patches.json）后再放开。
    void showGame() {
        load();
        LinearLayout box=new LinearLayout(activity); box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(24),dp(4),dp(24),dp(8));
        final Switch[] toggles=new Switch[GAME_PATCHES.length];
        for (int i=0;i<GAME_PATCHES.length;++i) {
            toggles[i]=toggle(box,GAME_PATCHES[i][1],"1".equals(get(GAME_PATCHES[i][0],GAME_PATCHES[i][3])));
            TextView note=new TextView(activity); note.setTextSize(12); note.setAlpha(0.65f);
            note.setText(UiText.get(activity, GAME_PATCHES[i][2])); note.setPadding(0,0,0,dp(6));
            box.addView(note);
        }
        TextView restartNote=new TextView(activity); restartNote.setTextSize(13); restartNote.setAlpha(0.7f);
        restartNote.setText(UiText.get(activity, "These are patches to the game: Apply restarts it (unsaved progress is lost)."));
        restartNote.setPadding(0,dp(8),0,0);
        box.addView(restartNote);
        ScrollView scroll=new ScrollView(activity); scroll.addView(box);
        new AlertDialog.Builder(activity).setTitle(UiText.get(activity, "Game settings")).setView(scroll)
            .setNegativeButton(UiText.get(activity, "Cancel"),null)
            .setPositiveButton(UiText.get(activity, "Apply"),(d,w) -> {
                Map<String,String> changed=new LinkedHashMap<>();
                for (int i=0;i<GAME_PATCHES.length;++i) changed.put(GAME_PATCHES[i][0],toggles[i].isChecked() ? "1" : "0");
                apply(changed);
            }).show();
    }
     */

    /* showCheats() 与 writeCheatState() 已注释掉（入口也随之在 GameActivity 里隐藏）：作弊在
     * Android 上根本不生效，属于误导入口。原因是 hook 根本没装上——
     * src/probe.c 的 install_cheats() 被 `#if defined(GUEST_CPU_NATIVE)` 包着，而
     * GUEST_CPU_NATIVE 只在 `__x86_64__` 时定义（src/guest_cpu.h:12）。Android 是 aarch64 交叉
     * 编译（tools/android/build/aarch64-toolchain.cmake 的 CMAKE_C_COMPILER_TARGET），x86-64
     * guest 跑在 FEXCore JIT 上，所以 probe.c 那段连调用带定义一起被编译掉了，源码注释写得很
     * 直接："Under the JIT ... the game runs without cheats, the health bar and the orb
     * multipliers"。gow3.ini 里的 cheat_health / cheat_item 会被 gow3_settings.cpp 读进
     * Gow3Settings::cheats[]，但没有任何 hook 去读这些 flag，等于写了没人用。
     * 附带：writeCheatState 写的 cheats.state 在本仓库也没有读取方（GOW3_CHEATS_FILE 只出现在
     * 注释里），所以界面上"运行中即时生效"那句本来也不成立。
     * 要接回来的前提是 probe.c 接上 JIT 的 hook 路径（guest_cpu_hook，注释标为 not yet wired）。
    void showCheats() {
        load();
        LinearLayout box=new LinearLayout(activity); box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(24),dp(4),dp(24),dp(8));
        final Switch[] toggles=new Switch[CHEATS.length];
        for (int i=0;i<CHEATS.length;++i) {
            toggles[i]=toggle(box,CHEATS[i][1],"1".equals(get(CHEATS[i][0],CHEATS[i][3])));
            TextView note=new TextView(activity); note.setTextSize(12); note.setAlpha(0.65f);
            note.setText(UiText.get(activity, CHEATS[i][2])); note.setPadding(0,0,0,dp(6));
            box.addView(note);
        }
        TextView restartNote=new TextView(activity); restartNote.setTextSize(13); restartNote.setAlpha(0.7f);
        restartNote.setText(UiText.get(activity, "For God of War III 1.09 offline play. They switch at once, while you play."));
        restartNote.setPadding(0,dp(8),0,0);
        box.addView(restartNote);
        ScrollView scroll=new ScrollView(activity); scroll.addView(box);
        new AlertDialog.Builder(activity).setTitle(UiText.get(activity, "Cheats")).setView(scroll)
            .setNegativeButton(UiText.get(activity, "Cancel"),null)
            .setPositiveButton(UiText.get(activity, "Apply"),(d,w) -> {
                Map<String,String> changed=new LinkedHashMap<>();
                for (int i=0;i<CHEATS.length;++i) changed.put(CHEATS[i][0],toggles[i].isChecked() ? "1" : "0");
                // The running game follows cheats.state (probe.c reads it): no restart.
                boolean ok=save(changed) && writeCheatState(new File(file.getParentFile(),"cheats.state"),
                    toggles[0].isChecked(),toggles[1].isChecked());
                android.widget.Toast.makeText(activity,ok ? "Cheats applied" : "The cheats could not be saved",
                    android.widget.Toast.LENGTH_SHORT).show();
            }).show();
    }

    // "10": infinite health on, items off (run-gow3.sh's GOW3_CHEATS_FILE), written whole then renamed.
    private static boolean writeCheatState(File state,boolean health,boolean items) {
        File temporary=new File(state.getPath()+".tmp");
        try (Writer w=new OutputStreamWriter(new FileOutputStream(temporary),"UTF-8")) {
            w.write((health ? "1" : "0")+(items ? "1" : "0")+"\n");
        } catch (Exception ex) { android.util.Log.e("God of War III","cheats: "+ex); return false; }
        return temporary.renameTo(state);
    }
     */

}
