package ro.cobrabm.fexdroid;

import android.content.Context;

import android.content.SharedPreferences;
import java.io.FileInputStream;
import java.util.Properties;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.Process;
import android.view.MotionEvent;
import android.view.View;



import java.io.File;

/**
 * 性能 HUD 悬浮层：横向单行文本
 * 「FPS 60 · GPU 42% · CPU 23%」画在半透明黑底圆角矩形上。FPS 来自 Gow3Present
 * 呈现帧计数器的 1 秒差分；GPU/CPU 占用由后台 HandlerThread 周期读系统计数文件，缺失时
 * 显示 N/A。拖动只消费落在 HUD 边界内的触摸，其余事件穿透到下层输入层。
 * 线程边界（design D6）：主线程只做 UI 与触摸，采样线程只做读数与差分；
 * Activity onDestroy 必须 {@link #release()}，保证无残留周期任务。
 */
final class PerfHudOverlay extends View {
    /** 采样周期（约 1 秒，spec「按固定周期刷新」）。 */
    private static final long TICK_MS = 1000L;
    /** GPU 全部候选不可读后，每隔这么多 tick 重新发现一次节点（spec「恢复后还原显示」）。 */
    private static final int GPU_REDISCOVER_TICKS = 5;
    /** 游戏进程扫描的节流周期（tick 数）：pid 失效后才重新扫 /proc。 */
    private static final int GAME_PID_RESCAN_TICKS = 10;
    /** HUD 距屏幕边缘的默认留白与默认停靠边距（dp）。 */
    private static final float MARGIN_DP = 8f;

    private final SharedPreferences prefs;
    /** 位置校验/默认位置计算用的纯逻辑（design D4）。 */
    private final float marginPx;

    private final Paint pBg = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint pText = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.SUBPIXEL_TEXT_FLAG);
    private final Paint pSep = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.SUBPIXEL_TEXT_FLAG);
    private final float textPx, padPx, lineH, cornerPx, gapPx, sepW;
    /** 最近一次绘制出的 HUD 矩形（视图坐标系）：触摸命中与拖动夹紧都用它。 */
    private final RectF hudRect = new RectF();
    /** 横向单行的基线（pad + 行高的视觉居中偏移）。 */
    private final float baseline;

    // ---- 采样快照：采样线程写、主线程读，volatile 保证可见性（design D6，不持锁绘制） ----
    private volatile int snapFps = 0;
    // 帧生成双帧率段（null = 未生效，显示单一帧率）。
    private volatile String snapFpsSegment;
    private volatile String snapGpu, snapCpu; // null = N/A（首轮差分或计数不可读）

    // ---- 采样状态（仅采样线程访问） ----
    private HandlerThread sampler;
    private Handler samplerHandler, uiHandler;
    private volatile boolean running;
    private long lastFrames = -1;      // -1 = 首帧未知，diffFrames 按 0 处理
    private final int cores = Runtime.getRuntime().availableProcessors();
    // CPU 回退链的各模式状态：/proc/stat → 游戏进程 stat → cpufreq 频率比值
    private long[] prevCpuSys;
    private long prevGameTicks = -1, prevGameNanos;
    private int gamePid = -1, gamePidScanCooldown;
    // GPU 节点发现状态：null = 尚未发现
    private String[] gpuPaths;
    private int gpuFailures;

    // ---- 拖动状态（仅主线程访问） ----
    private float hudX, hudY;          // Position is derived from the anchor and actual measured HUD size.
    private final float density = getResources().getDisplayMetrics().density;
    private int anchor = 1, offsetXd = 0, offsetYd = 0;
    private boolean dragging;
    private float grabDx, grabDy;

    /** GPU 候选注入点：生产用默认清单+扫描根，宿主单测注入临时目录。 */
    private String[] gpuStaticPaths = PerfHudMetrics.DEFAULT_GPU_PATHS;
    private String[] gpuScanRoots = PerfHudMetrics.SCAN_ROOTS;

    private final Context context;

    PerfHudOverlay(Context context) {
        super(context);
        this.context = context;
        this.prefs = context.getSharedPreferences("gow3", Context.MODE_PRIVATE);
        float density = context.getResources().getDisplayMetrics().density;
        marginPx = MARGIN_DP * density;
        textPx = 12f * density;      // 与抽屉摘要文本（12sp）一致的字号
        padPx = 6f * density;
        lineH = textPx * 1.35f;
        cornerPx = 4f * density;
        gapPx = padPx;               // 段间距
        pBg.setColor(Color.argb(180, 0, 0, 0)); // 半透明黑底
        pText.setTypeface(Typeface.MONOSPACE);
        pText.setTextSize(textPx);
        pSep.setTypeface(Typeface.MONOSPACE);
        pSep.setTextSize(textPx);
        pSep.setColor(0xff8e9097);   // 分隔点用抽屉摘要的灰色
        sepW = pSep.measureText(" · ");
        baseline = padPx + lineH * 0.78f; // 手工基线：视觉上垂直居中
        uiHandler = new Handler(Looper.getMainLooper());
        setElevation(density * 2f); // 盖在 SurfaceView 之上，仍低于抽屉（drawer 有 16dp elevation）
    }

    /** 开关 HUD 并同步采样线程的启停；GameActivity 抽屉行与启动恢复都走这里。 */
    void setActive(boolean on) {
        setVisibility(on ? VISIBLE : GONE);
        if (!on) {
            // Disabling must stop the worker: otherwise the next toggle-on has
            // a non-null sampler with no tick scheduled and the HUD freezes.
            release();
        } else {
            running = true;
            if (sampler == null) startSampling();
        }
    }

    private void startSampling() {
        sampler = new HandlerThread("perf-hud", Thread.MIN_PRIORITY);
        sampler.start();
        samplerHandler = new Handler(sampler.getLooper());
        samplerHandler.post(this::tick);
    }

    /** 停止采样并退出采样线程；Activity 销毁时必须调用（spec「退出游戏停止采样」）。 */
    void release() {
        running = false;
        if (sampler != null) {
            sampler.quitSafely();
            sampler = null;
            samplerHandler = null;
        }
        uiHandler.removeCallbacksAndMessages(null);
    }

    /** 一次采样 tick：读帧计数器做 FPS 差分、读 GPU/CPU 计数，然后回主线程重绘。 */
    private void tick() {
        if (running && samplerHandler != null) {
            try { sampleFps(); } catch (Throwable ignored) {}
            try { sampleCpu(); } catch (Throwable ignored) {}
            try { sampleGpu(); } catch (Throwable ignored) {}
            uiHandler.post(this::invalidate);
            samplerHandler.postDelayed(this::tick, TICK_MS);
        }
    }

    /** 帧率段文本：帧生成生效时为「源→上屏 LSFG Nx」，否则单一帧率。 */
    private String fpsText() {
        String seg = snapFpsSegment;
        return seg != null ? "FPS " + seg : "FPS " + snapFps;
    }

    /** Atomic native presenter telemetry: source/presented FPS and actual 2x/3x/4x. */
    private static float[] readFramegenStats(File file) {
        if (!file.isFile()) return null;
        try (FileInputStream input = new FileInputStream(file)) {
            Properties p = new Properties();
            p.load(input);
            int mult = Integer.parseInt(p.getProperty("multiplier", "0"));
            float source = Float.parseFloat(p.getProperty("source_fps", "0"));
            float presented = Float.parseFloat(p.getProperty("presented_fps", "0"));
            if (mult < 2 || mult > 4 || source <= 0 || presented <= 0) return null;
            return new float[]{source, presented, mult};
        } catch (Exception e) { return null; }
    }

    /** FPS：呈现帧计数器 1 秒窗口差分；帧生成生效时改用游戏侧遥测文件
     *  （framegen.stats：源/上屏双帧率 + LSFG 倍率，presenter 每秒原子写，
     *  change add-native-frame-generation）。文件缺失/未生效时回退直通语义。 */
    private void sampleFps() {
        float[] fg = readFramegenStats(new File(context.getFilesDir(), "gow3port/framegen.stats"));
        if (fg != null) {
            int src = Math.round(fg[0]), pres = Math.round(fg[1]);
            snapFps = pres;
            snapFpsSegment = PerfHudMetrics.fpsSegment(src, pres, (int)fg[2]);
            lastFrames = Gow3Present.framesIfLoaded(); // 保持直通计数器基准新鲜
            return;
        }
        long now = Gow3Present.framesIfLoaded();
        snapFps = PerfHudMetrics.diffFrames(lastFrames, now);
        snapFpsSegment = null;
        lastFrames = now;
    }

    /**
     * CPU 三级回退：/proc/stat 整机差分 → SELinux 拒绝时游戏子进程 utime+stime
     * 差分（同 uid 恒可读，比整机更能反映游戏负载）→ 进程不可见时 cpufreq
     * 频率比值估算。每级失败只影响本级，不允许抛出中断采样循环。
     */
    private void sampleCpu() {
        int usage = PerfHudMetrics.INVALID;
        long now = System.nanoTime();
        long[] sys = PerfHudMetrics.cpuTotals(PerfHudMetrics.readFirstLine("/proc/stat"));
        if (sys != null) {
            usage = PerfHudMetrics.cpuUsage(prevCpuSys, sys);
            prevCpuSys = sys;
            prevGameTicks = -1; // 回到整机模式后丢弃进程档基准
        } else {
            prevCpuSys = null;
            int pid = findGamePid();
            long[] f = pid > 0
                    ? PerfHudMetrics.procStatFields(PerfHudMetrics.readFirstLine("/proc/" + pid + "/stat"))
                    : null;
            if (f != null) {
                usage = PerfHudMetrics.processCpuUsage(prevGameTicks, f[1], prevGameNanos, now, cores);
                prevGameTicks = f[1];
                prevGameNanos = now;
            } else {
                prevGameTicks = -1;
                usage = PerfHudMetrics.cpuFreqLoad(
                        readFreqs("/sys/devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq"),
                        readFreqs("/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq"));
            }
        }
        snapCpu = usage >= 0 ? usage + "%" : null;
    }

    /** 逐核读一个 cpufreq 文件；读不到的核记 0，cpuFreqLoad 会自动跳过。 */
    private long[] readFreqs(String pattern) {
        long[] out = new long[cores];
        for (int i = 0; i < cores; i++) {
            String text = PerfHudMetrics.readFirstLine(String.format(java.util.Locale.US, pattern, i));
            if (text != null) {
                try { out[i] = Long.parseLong(text.trim().split("\\s+")[0]); }
                catch (NumberFormatException ignored) {}
            }
        }
        return out;
    }

    /**
     * 在 /proc 里发现游戏子进程：comm 匹配 {@link PerfHudMetrics#GAME_COMM}
     * （game 是 launcher 的同 uid 子进程，stat 恒可读；exec 前后的 sh 包装也
     * 不影响 comm 匹配）。缓存命中后只在进程消失时重扫，扫描按 tick 节流。
     */
    private int findGamePid() {
        if (gamePid > 0 && PerfHudMetrics.GAME_COMM.equals(
                PerfHudMetrics.procComm(PerfHudMetrics.readFirstLine("/proc/" + gamePid + "/stat")))) {
            return gamePid; // 缓存仍有效
        }
        gamePid = -1;
        if (gamePidScanCooldown > 0) { gamePidScanCooldown--; return -1; }
        gamePidScanCooldown = GAME_PID_RESCAN_TICKS;
        File[] dirs = new File("/proc").listFiles(d -> {
            String n = d.getName();
            return !n.isEmpty() && Character.isDigit(n.charAt(0));
        });
        if (dirs != null) {
            for (File dir : dirs) {
                String line = PerfHudMetrics.readFirstLine(new File(dir, "stat").getPath());
                if (!PerfHudMetrics.GAME_COMM.equals(PerfHudMetrics.procComm(line))) continue;
                long[] f = PerfHudMetrics.procStatFields(line);
                if (f != null && f[0] == Process.myPid()) { gamePid = Integer.parseInt(dir.getName()); break; }
            }
        }
        return gamePid;
    }

    /**
     * GPU：节点发现一次固定使用；全部候选连续 GPU_REDISCOVER_TICKS 个 tick 读不到时
     * 重新发现，满足「计数来源恢复后恢复显示」。
     */
    private void sampleGpu() {
        if (gpuPaths == null || (gpuPaths.length == 0
                && ++gpuFailures >= GPU_REDISCOVER_TICKS)) {
            gpuFailures = 0;
            gpuPaths = PerfHudMetrics.discoverGpuPaths(gpuStaticPaths, gpuScanRoots);
        }
        if (gpuPaths.length == 0) { snapGpu = null; return; }
        int value = PerfHudMetrics.INVALID;
        for (String path : gpuPaths) {
            value = readGpuSample(path);
            if (value >= 0) break; //
        }
        if (value >= 0) {
            gpuFailures = 0;
            snapGpu = value + "%";
        } else if (++gpuFailures >= GPU_REDISCOVER_TICKS) {
            gpuFailures = 0;
            gpuPaths = null; // 下个 tick 重新发现（设备固件/权限可能已变化）
            snapGpu = null;
        } else {
            snapGpu = null;
        }
    }

    /** 按路径形态选解析器：gpubusy 是 busy/total 即时比值，MTK 是 ACTIVE= token，其余取首个数字。 */
    private int readGpuSample(String path) {
        if (path.endsWith("/gpubusy")) {
            return PerfHudMetrics.gpuBusyRatio(PerfHudMetrics.readFirstLine(path));
        }
        if (path.endsWith("/mtk_mali/utilization")) {
            return PerfHudMetrics.mtkActive(PerfHudMetrics.readFirstLine(path));
        }
        return PerfHudMetrics.parsePercent(PerfHudMetrics.readFirstLine(path));
    }

    /** 宿主单测专用：注入假节点路径清单/扫描根（临时目录），不影响生产路径。 */
    void setGpuSourcesForTest(String[] staticPaths, String[] scanRoots) {
        gpuStaticPaths = staticPaths;
        gpuScanRoots = scanRoots;
        gpuPaths = null;
    }

    private String gpuText() { return "GPU " + (snapGpu != null ? snapGpu : "N/A"); }
    private String cpuText() { return "CPU " + (snapCpu != null ? snapCpu : "N/A"); }

    private void updateMetrics() {
        // A second line prevents 2x/3x/4x LSFG from pushing GPU/CPU off-screen.
        float first = pText.measureText(fpsText());
        float second = pText.measureText(gpuText()) + sepW + pText.measureText(cpuText());
        float available = Math.max(1f, getWidth() - marginPx * 2);
        float width = Math.min(available, Math.max(first, second) + padPx * 2);
        hudRect.set(0, 0, width, lineH * 2 + padPx * 3);
    }
    private void alignToAnchor() {
        float w = hudRect.width();
        float base = anchor == 0 ? marginPx : anchor == 4 ? (getWidth() - w) * 0.5f
                : getWidth() - marginPx - w;
        hudX = Math.max(marginPx, Math.min(base + offsetXd * density,
                Math.max(marginPx, getWidth() - marginPx - w)));
        hudY = Math.max(marginPx, Math.min(marginPx + offsetYd * density,
                Math.max(marginPx, getHeight() - marginPx - hudRect.height())));
    }
    /** Called on the main thread when the launcher or native in-game menu edits gow3.ini. */
    void setConfiguration(HudConfig cfg) {
        if (anchor == cfg.anchor && offsetXd == cfg.dx && offsetYd == cfg.dy) return;
        anchor = cfg.anchor;
        offsetXd = cfg.dx;
        offsetYd = cfg.dy;
        if (!dragging) alignToAnchor();
        invalidate();
    }

    private float[] segmentWidths() {
        return new float[]{
            pText.measureText(fpsText()),
            pText.measureText("GPU " + (snapGpu != null ? snapGpu : "N/A")),
            pText.measureText("CPU " + (snapCpu != null ? snapCpu : "N/A")),
        };
    }

    @Override protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
        if (w <= 0 || h <= 0) return;
        updateMetrics();
        alignToAnchor();
    }

    @Override protected void onDraw(Canvas c) {
        super.onDraw(c);
        if (getWidth() <= 0 || getHeight() <= 0) return;
        updateMetrics();
        if (!dragging) alignToAnchor(); // Recalculate whenever LSFG changes text width.
        c.save();
        c.translate(hudX, hudY);
        c.drawRoundRect(hudRect, cornerPx, cornerPx, pBg);
        // Always keep FPS and GPU/CPU on separate lines, with the original colors.
        pText.setColor(0xff76ff03);
        c.save();
        c.clipRect(padPx, 0, hudRect.width() - padPx, hudRect.height());
        c.drawText(fpsText(), padPx, baseline, pText);
        float row2 = baseline + lineH + padPx;
        float x = padPx;
        pText.setColor(0xffe040fb);
        c.drawText(gpuText(), x, row2, pText);
        x += pText.measureText(gpuText());
        c.drawText(" · ", x, row2, pSep);
        x += sepW;
        pText.setColor(0xff00e5ff);
        c.drawText(cpuText(), x, row2, pText);
        c.restore();
        c.restore();
    }

    @Override public boolean onTouchEvent(MotionEvent e) {
        // 触摸穿透（design D1）：只有 DOWN 落在 HUD 边界内才消费整条手势；其余一律
        // 返回 false，由父容器继续分发给下层（controllerOverlay / 游戏）。
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                if (!insideHud(e.getX(), e.getY())) return false;
                dragging = true;
                grabDx = e.getX() - hudX; grabDy = e.getY() - hudY;
                return true;
            case MotionEvent.ACTION_MOVE:
                if (!dragging) return false;
                moveTo(e.getX() - grabDx, e.getY() - grabDy);
                return true;
            case MotionEvent.ACTION_UP:
                if (!dragging) return false;
                dragging = false;
                // Preserve the exact new position in the same INI used by the in-game menu.
                float base = anchor == 0 ? marginPx : anchor == 4 ? (getWidth() - hudRect.width()) * 0.5f
                        : getWidth() - marginPx - hudRect.width();
                offsetXd = Math.max(-300, Math.min(300, Math.round((hudX - base) / density)));
                offsetYd = Math.max(0, Math.min(300, Math.round((hudY - marginPx) / density)));
                java.util.Map<String,String> changed = new java.util.LinkedHashMap<>();
                changed.put(HudConfig.DX, String.valueOf(offsetXd));
                changed.put(HudConfig.DY, String.valueOf(offsetYd));
                HudConfig.update(new File(context.getFilesDir(), "gow3port/gow3.ini"), changed);
                return true;
            case MotionEvent.ACTION_CANCEL:
                dragging = false;
                return true;
            default:
                return dragging;
        }
    }

    private boolean insideHud(float x, float y) {
        return x >= hudX && x <= hudX + hudRect.width() && y >= hudY && y <= hudY + hudRect.height();
    }

    /** 拖动落点夹紧在可视范围内（spec「不出屏幕可视范围」）。 */
    private void moveTo(float x, float y) {
        hudX = Math.max(0, Math.min(x, Math.max(0, getWidth() - hudRect.width())));
        hudY = Math.max(0, Math.min(y, Math.max(0, getHeight() - hudRect.height())));
        invalidate();
    }
}
