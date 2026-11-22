package com.gow3.android.data

import android.app.Activity
import android.content.Context
import android.os.SystemClock
import ro.cobrabm.fexdroid.RuntimeInstaller
import ro.cobrabm.fexdroid.SotcPaths
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** Recompile the selected SotC PS4 image with AOT on the Android phone itself. */
internal class SotcAotBuildManager(
    private val activity: Activity,
    private val onState: (Boolean, String?) -> Unit,
) {
    private val busy = AtomicBoolean()
    private val worker = Executors.newSingleThreadExecutor()
    @Volatile private var current: Process? = null
    fun isBusy() = busy.get()
    private fun status(text: String?, running: Boolean = true) {
        activity.runOnUiThread { onState(running, text) }
    }
    fun start() {
        if (activity.packageName != "com.sotc.android.daedalus") return
        if (!busy.compareAndSet(false, true)) return
        status("Preparando AOT ARM64 (sem FEX e sem TSO)…")
        worker.execute {
            val files = activity.filesDir
            val base = File(files, "sotcport")
            var last = "AOT"
            try {
                val pref = activity.getSharedPreferences(SotcPaths.prefsName(activity), Context.MODE_PRIVATE)
                val game = pref.getString("game_dir", null)
                    ?: throw IllegalStateException("Selecione a pasta do jogo primeiro")
                val selected = File(game)
                require(File(selected, "eboot.bin").isFile) { "eboot.bin não encontrado no jogo selecionado" }
                RuntimeInstaller.ensure(activity, files) { status(it) }
                val script = File(base, "run-sotc-bionic.sh")
                val tool = File(activity.applicationInfo.nativeLibraryDir, "libbbrecomp.so")
                require(script.isFile && tool.isFile) {
                    "Este APK não inclui o compilador AOT ARM64"
                }
                val cfg = Gow3Ini.read(File(base, "sotc.ini"))
                fun opt(name: String, default: String = "0") = cfg[name] ?: default
                val render = when (opt("sotc_resolution", "720p")) {
                    "360p" -> "640x360"; "540p" -> "960x540"
                    "900p" -> "1600x900"; "1080p" -> "1920x1080"; else -> "1280x720"
                }
                val fps = opt("sotc_fps_mode", "fps60game")
                val modes = mutableListOf<String>()
                if (fps == "fps60" || fps == "fps60game") modes.add(fps)
                if (opt("sotc_af16") == "1") modes.add("af16")
                val blur = opt("sotc_blur_suppression", "1") != "0"
                val cvars = "doIndexBufferCulling=0 doSunShadowIndexBufferCulling=0" +
                    if (blur) " r_motionBlurEnable=0" else ""
                val perf = mutableListOf<String>()
                if (opt("sotc_bachata_bloom", "1") != "0") perf.add("bloom")
                if (blur) perf.add("blur")
                if (opt("sotc_bachata_ssr") == "1") perf.add("ssr")
                if (opt("sotc_bachata_fog") == "1") perf.add("fog")
                if (opt("sotc_bachata_shadows") == "1") perf.add("shadows")
                val process = ProcessBuilder("/system/bin/sh", script.absolutePath, "compile")
                    .directory(base).redirectErrorStream(true)
                val env = process.environment()
                env.clear()
                env["FXD_FILES"] = files.absolutePath
                env["PATH"] = "/system/bin"
                env["HOME"] = File(files, "home/sotcport").absolutePath
                env["TMPDIR"] = File(base, "tmp").absolutePath
                env["LD_LIBRARY_PATH"] = File(base, "arm64/lib").absolutePath + ":" +
                    File(base, "arm64/python/lib").absolutePath
                env["SOTC_AOT_COMPILER_BINARY"] = tool.absolutePath
                env["SOTC_GAME_DIR"] = selected.absolutePath
                env["SOTC_RENDER"] = render
                env["SOTC_MODES"] = modes.joinToString(",")
                // Compile and launch MUST prepare the exact same guest image.
                // GameActivity forwards sotc_sun_cascades to run-sotc-bionic.sh;
                // the script appends r_enableCascadeShadows=0 for mode 0.
                // Previously the AOT builder omitted this setting, compiled mode 5,
                // and the launch correctly rejected the mismatched AOT image.
                val sunCascades = opt("sotc_sun_cascades", "5")
                    .takeIf { it == "0" || it == "1" || it == "2" ||
                              it == "3" || it == "5" } ?: "5"
                env["SOTC_SUN_CASCADES"] = sunCascades
                env["SOTC_CVARS"] = cvars
                env["SOTC_BACHATA_PERF"] = perf.joinToString(",")
                status("Preparando eboot, PRX e patches atuais…")
                val proc = process.start()
                current = proc
                var lastProgress = ""
                var lastUpdate = 0L
                val log = File(base, "logs/aot-on-device-build.log")
                log.parentFile?.mkdirs()
                log.outputStream().bufferedWriter().use { writer ->
                    proc.inputStream.bufferedReader().useLines { lines ->
                        lines.forEach { line ->
                            writer.appendLine(line)
                            writer.flush()
                            val now = SystemClock.elapsedRealtime()
                            if (line.startsWith("BBR-PROGRESS ")) {
                                val parts = line.split(' ')
                                val done = parts.getOrNull(2)?.toDoubleOrNull() ?: 0.0
                                val total = parts.getOrNull(3)?.toDoubleOrNull() ?: 0.0
                                val pct = if (total > 0) ((done / total) * 100).toInt().coerceIn(0,100) else 0
                                val progress = "AOT ARM64 — " + parts.getOrNull(1) + " " + pct + "%"
                                if (progress != lastProgress && now - lastUpdate > 700) {
                                    lastProgress = progress
                                    lastUpdate = now
                                    status(progress)
                                }
                            } else if (line.contains("SOTC_AOT_READY")) {
                                status("AOT recompilado e validado. Biblioteca ativada.")
                            } else if (line.contains("BBR-ERROR") || line.contains("AOT preflight:")) {
                                last = line.takeLast(200)
                                status(last)
                            }
                        }
                    }
                }
                val code = proc.waitFor()
                current = null
                if (code != 0) throw IllegalStateException("Compilador saiu com erro " + code + ". " + last)
                status("AOT ARM64 pronto. O próximo início usará a biblioteca recompilada.", false)
            } catch (e: Exception) {
                status("Falha no AOT: " + e.message + ". Veja logs/aot-on-device-build.log", false)
            } finally {
                busy.set(false)
                current = null
            }
        }
    }
}
