package com.gow3.android.data

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File
import java.nio.charset.StandardCharsets

/**
 * Single source of truth for the upstream in-process Bloodframe integration.
 * The native presenter watches <files>/gow3port/framegen.state while the
 * launcher stores user preference in the existing "gow3" SharedPreferences.
 */
internal class FrameGenStorage(private val context: Context) {
    private val prefs = context.getSharedPreferences("gow3", Context.MODE_PRIVATE)
    private val base = File(context.filesDir, "gow3port")
    private val state = File(base, "framegen.state")
    private val dll = File(base, "Lossless.dll")

    fun enabledMultiplier(): Int = prefs.getInt("framegen_multiplier", 0).takeIf { it in 2..4 } ?: 0
    fun preferredMultiplier(): Int = prefs.getInt("framegen_preferred_multiplier", 2).coerceIn(2, 4)
    fun hasDll(): Boolean = dll.isFile && dll.length() > 0

    /** Atomic file hand-off, parsed by Gow3LsfgState::Watcher every 250 ms. */
    fun setMultiplier(requested: Int): Boolean {
        val multiplier = if (requested in 2..4) requested else 0
        if (multiplier > 0 && !hasDll()) return false
        if (!base.isDirectory && !base.mkdirs()) return false
        val temp = File(base, "framegen.state.tmp")
        return try {
            val text = buildString {
                appendLine("multiplier=$multiplier")
                appendLine("flow=0.80")
                appendLine("performance=1")
                appendLine("fp16=1")
            }
            temp.outputStream().use { out ->
                out.write(text.toByteArray(StandardCharsets.US_ASCII))
                out.flush()
                (out as java.io.FileOutputStream).fd.sync()
            }
            if (!temp.renameTo(state)) {
                temp.delete()
                return false
            }
            prefs.edit().putInt("framegen_multiplier", multiplier).apply()
            if (multiplier >= 2)
                prefs.edit().putInt("framegen_preferred_multiplier", multiplier).apply()
            true
        } catch (_: Exception) {
            temp.delete()
            false
        }
    }

    /** User must provide their own genuine Lossless.dll; it is never bundled. */
    fun importDll(uri: Uri): Boolean {
        val resolver = context.contentResolver
        val name = try {
            resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
                val col = it.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (col >= 0 && it.moveToFirst()) it.getString(col) else null
            }
        } catch (_: Exception) { null } ?: uri.lastPathSegment?.substringAfterLast('/')
        if (!name.equals("Lossless.dll", ignoreCase = true)) return false
        if (!base.isDirectory && !base.mkdirs()) return false
        val temp = File(base, ".Lossless.dll.tmp")
        var count = 0L
        return try {
            val input = resolver.openInputStream(uri) ?: return false
            input.use { from ->
                temp.outputStream().use { to ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = from.read(buf)
                        if (n < 0) break
                        count += n
                        if (count > 128L * 1024 * 1024) throw IllegalArgumentException("DLL too large")
                        to.write(buf, 0, n)
                    }
                    to.flush()
                }
            }
            if (count == 0L || !temp.renameTo(dll)) {
                temp.delete()
                false
            } else true
        } catch (_: Exception) {
            temp.delete()
            false
        }
    }
}
