// SPDX-License-Identifier: GPL-3.0-only
// Adapted from The412Banner/Bannerlator 0ab047311ccc55b2911d984727d2d57ac6c0ebf7.
package ro.cobrabm.fexdroid

import android.util.Log

object KgslBusy {
    private const val TAG = "HudGpu"
    @JvmStatic private external fun nativeOpen(error: IntArray): Long
    @JvmStatic private external fun nativeMode(handle: Long): Int
    @JvmStatic private external fun nativeRun(handle: Long, on: Boolean)
    @JvmStatic private external fun nativeRead(handle: Long, out: LongArray): Boolean
    @JvmStatic private external fun nativeClose(handle: Long)
    private val loaded: Boolean by lazy {
        runCatching { System.loadLibrary("gpuusage") }
            .onFailure { Log.w(TAG, "gpuusage library load failed: $it") }.isSuccess
    }
    class Reader internal constructor(private var handle: Long) : AutoCloseable {
        @Synchronized fun run(on: Boolean) {
            if (handle != 0L) nativeRun(handle, on)
        }
        val mode: Int = if (handle != 0L) runCatching { nativeMode(handle) }.getOrDefault(0) else 0
        @Synchronized fun counts(): LongArray? {
            if (handle == 0L) return null
            val out = LongArray(3)
            return if (nativeRead(handle, out)) out else null
        }
        @Synchronized override fun close() {
            if (handle != 0L) nativeClose(handle)
            handle = 0L
        }
    }
    const val MODE_RINGBUFFER = 1
    const val MODE_CONTEXTS = 2
    @Volatile var status = "not tried"
    fun open(): Reader? {
        if (!loaded) {
            status = "gpuusage library did not load"
            return null
        }
        val error = IntArray(1)
        val handle = runCatching { nativeOpen(error) }.getOrDefault(0L)
        if (handle == 0L) {
            status = "open failed (negative errno ${error[0]})"
            Log.i(TAG, "kgsl memstore unavailable (errno ${error[0]})")
            return null
        }
        val reader = Reader(handle)
        status = if (reader.mode == MODE_CONTEXTS)
            "per-context timestamps (hardware scheduling)" else "ringbuffer timestamps"
        Log.i(TAG, "kgsl reader: $status")
        return reader
    }
}
