package com.gow3.android.data

import android.app.Activity
import android.content.Context
import android.os.SystemClock
import ro.cobrabm.fexdroid.RuntimeInstaller
import ro.cobrabm.fexdroid.SotcPaths
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Mandatory, on-device native AOT before the first play.
 * A fast verification also reuses earlier verified patch profiles; recompilation
 * only runs for a new game or an effect combination that has not been compiled.
 * Native ARM64, even on failed verification.
 */
internal class SotcAotBuildManager(
    private val activity: Activity,
    private val onState: (Boolean, String?) -> Unit,
) {
    private val busy = AtomicBoolean(false)
    private val worker = Executors.newSingleThreadExecutor()
    @Volatile private var current: Process? = null

    fun isBusy(): Boolean = busy.get()
    private fun status(text: String?, running: Boolean = true) {
        activity.runOnUiThread { onState(running, text) }
    }

    /** Explicit rebuild for a developer or recovery action. */
    fun start() { run(true, null) }

    /** Used by Play. A game must not launch before AOT has been verified. */
    fun ensureReadyThen(onReady: () -> Unit) { run(false, onReady) }

    private fun run(force: Boolean, onReady: (() -> Unit)?) {
        if (activity.packageName != "com.sotc.android.daedalus") return
        if (!busy.compareAndSet(false, true)) return
        status("Verificando código nativo ARM64 para o jogo e patches selecionados…")
        worker.execute {
            var ready = false
            var finalMessage = "AOT ARM64 pronto"
            val files = activity.filesDir
            val base = File(files, "sotcport")
            try {
                val pref = activity.getSharedPreferences(SotcPaths.prefsName(activity), Context.MODE_PRIVATE)
                val gamePath = pref.getString("game_dir", null)
                    ?: throw IllegalStateException("Selecione a pasta do jogo primeiro")
                val selected = File(gamePath)
                require(File(selected, "eboot.bin").isFile) {
                    "eboot.bin não encontrado na pasta selecionada"
                }
                RuntimeInstaller.ensure(activity, files) { status(it) }
                val script = File(base, "run-sotc-bionic.sh")
                val tool = File(activity.applicationInfo.nativeLibraryDir, "libbbrecomp.so")
                require(script.isFile && tool.isFile) {
                    "Este APK não inclui o compilador ARM64"
                }
                val cfg = Gow3Ini.read(File(base, "sotc.ini"))
                fun opt(name: String, default: String = "0") = cfg[name] ?: default
                val modes = mutableListOf<String>()
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
                val env = hashMapOf(
                    "FXD_FILES" to files.absolutePath,
                    "PATH" to "/system/bin",
                    "HOME" to File(files, "home/sotcport").absolutePath,
                    "TMPDIR" to File(base, "tmp").absolutePath,
                    "LD_LIBRARY_PATH" to File(base, "arm64/lib").absolutePath + ":" +
                        File(base, "arm64/python/lib").absolutePath,
                    "SOTC_AOT_COMPILER_BINARY" to tool.absolutePath,
                    "SOTC_GAME_DIR" to selected.absolutePath,
                    "SOTC_RENDER" to when(opt("sotc_resolution","720p")) {
                        "540p" -> "960x540"
                        "360p" -> "640x360"
                        else -> "1280x720"
                    },
                    "SOTC_MODES" to modes.joinToString(","),
                    // Sun cascade experimentation was removed; original engine profile.
                    "SOTC_SUN_CASCADES" to "5",
                    "SOTC_CVARS" to cvars,
                    "SOTC_BACHATA_PERF" to perf.joinToString(","),
                )
                val log = File(base, "logs/aot-on-device-build.log")
                log.parentFile?.mkdirs()
                var last = "AOT"
                fun execute(mode: String): Int {
                    val command = ProcessBuilder("/system/bin/sh", script.absolutePath, mode)
                        .directory(base).redirectErrorStream(true)
                    command.environment().apply { clear(); putAll(env) }
                    val proc = command.start()
                    current = proc
                    var lastProgress = ""
                    var lastUpdate = 0L
                    log.appendText("\n--- SotC AOT ${mode}, ${System.currentTimeMillis()} ---\n")
                    java.io.FileOutputStream(log, true).bufferedWriter().use { writer ->
                        proc.inputStream.bufferedReader().useLines { lines ->
                            lines.forEach { line ->
                                writer.appendLine(line)
                                if (line.startsWith("BBR-PROGRESS ")) {
                                    val parts = line.split(' ')
                                    val done = parts.getOrNull(2)?.toDoubleOrNull() ?: 0.0
                                    val total = parts.getOrNull(3)?.toDoubleOrNull() ?: 0.0
                                    val pct = if (total > 0.0)
                                        ((done / total) * 100).toInt().coerceIn(0, 100) else 0
                                    val progress = "AOT ARM64 — " + parts.getOrNull(1) + " " + pct + "%"
                                    val now = SystemClock.elapsedRealtime()
                                    if (progress != lastProgress && now - lastUpdate > 700) {
                                        lastProgress = progress
                                        lastUpdate = now
                                        status(progress)
                                    }
                                } else if (line.startsWith("SOTC_AOT_READY")) {
                                    status("Código AOT validado e ativado.")
                                } else if (line.contains("BBR-ERROR") ||
                                           line.contains("AOT preflight:")) {
                                    last = line.takeLast(200)
                                }
                            }
                        }
                        writer.flush()
                    }
                    val code = proc.waitFor()
                    current = null
                    return code
                }
                if (!force) {
                    status("Verificando AOT (sem executar o jogo)…")
                    if (execute("verify") == 0) {
                        ready = true
                        finalMessage = "AOT validado; iniciando jogo."
                    } else {
                        status("Compilação ARM64 obrigatória: primeiro acesso ou patches alterados…")
                    }
                }
                if (!ready) {
                    status("Compilando o jogo para ARM64 (tradução ARM64 nativa)…")
                    val code = execute("compile")
                    if (code != 0) throw IllegalStateException(
                        "Compilador saiu com erro $code. $last"
                    )
                    ready = true
                    finalMessage = "AOT ARM64 compilado e validado."
                }
            } catch (e: Exception) {
                finalMessage = "Falha no AOT: " + e.message +
                    ". Consulte logs/aot-on-device-build.log"
            } finally {
                current = null
                busy.set(false)
                status(finalMessage, false)
                if (ready && onReady != null) activity.runOnUiThread {
                    if (!activity.isFinishing && !activity.isDestroyed) onReady()
                }
            }
        }
    }
}
