package com.gow3.android.data

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import ro.cobrabm.fexdroid.SotcPaths
import com.gow3.android.R
import java.io.File
import java.io.FileInputStream

/** 一次日志导出尝试的结果。Cancelled 表示用户在文件选择器中退出了。 */
internal sealed class LogResult {
    data class Success(val message: String) : LogResult()
    object Cancelled : LogResult()
    data class Failed(val message: String) : LogResult()
}

/**
 * 负责 God of War III 运行时日志：将 `logs/` 目录树（例如 GameActivity 写入的
 * `android-game.log`）导出为玩家通过 Storage Access Framework 选择的 `.zip`。
 * 只读取 `filesDir/gow3port/logs`；运行时、gow3.ini、运行时安装、存档和游戏文件
 * 绝不被修改。导出是只读快照，因此导出期间运行游戏只会捕获当时已刷盘的字节。
 */
internal class LogManager(private val activity: Activity) {

    companion object {
        /** 区别于 GameFolderManager 的 1001/1002 和 SaveManager 的 1004/1005。 */
        const val REQUEST_EXPORT = 1006
        private const val DEFAULT_EXPORT_NAME = "GodOfWar3-Logs"
    }

    /** 由 [launchExport] 设置，由 [onActivityResult] 消费。 */
    private var pending: ((LogResult) -> Unit)? = null

    /** launcher 的运行时日志目录，即 GameActivity 写入 `android-game.log` 的目录。 */
    fun logsDir(): File = File(activity.filesDir, "${SotcPaths.baseName(activity)}/logs")

    /**
     * 打开系统“另存为”选择器。当没有日志时，立即以失败调用 [onResult]，且不显示
     * 选择器。其他情况下，结果通过 activity 的 legacy 回调经由 [onActivityResult] 到达。
     */
    fun launchExport(onResult: (LogResult) -> Unit) {
        if (!LogArchive.hasLogs(logsDir())) {
            onResult(LogResult.Failed(activity.getString(R.string.log_no_logs)))
            return
        }
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/zip"
            putExtra(Intent.EXTRA_TITLE, "${if (SotcPaths.isSotc(activity)) "ShadowOfTheColossus-Logs" else DEFAULT_EXPORT_NAME}-${LogArchive.stamp()}.zip")
        }
        pending = onResult
        try {
            activity.startActivityForResult(intent, REQUEST_EXPORT)
        } catch (ex: Exception) {
            pending = null
            onResult(LogResult.Failed(activity.getString(R.string.no_file_picker_fmt, ex.message ?: activity.getString(R.string.unknown_error))))
        }
    }

    /** @return 当请求属于我们且已被消费时返回 true。 */
    fun onActivityResult(requestCode: Int, resultCode: Int, intent: Intent?): Boolean {
        if (requestCode != REQUEST_EXPORT) return false
        val callback = pending
        pending = null
        if (callback == null) return true
        val uri = intent?.data
        if (resultCode != Activity.RESULT_OK || uri == null) {
            callback(LogResult.Cancelled)
            return true
        }
        Thread {
            val result = exportTo(uri)
            activity.runOnUiThread { callback(result) }
        }.start()
        return true
    }

    /**
     * 先把日志目录树打包成临时 zip（SAF 流不可 seek），再复制到选择器返回的 URI。
     * 无论成功或失败，临时文件始终会被删除。
     */
    private fun exportTo(uri: Uri): LogResult {
        val logs = logsDir()
        if (!LogArchive.hasLogs(logs)) return LogResult.Failed(activity.getString(R.string.log_no_logs))
        val temporary = File(activity.filesDir, "${SotcPaths.baseName(activity)}/.export-logs.tmp")
        temporary.delete()
        return try {
            LogArchive.pack(logs, temporary)
            val output = activity.contentResolver.openOutputStream(uri)
                ?: return LogResult.Failed(activity.getString(R.string.log_write_failed))
            output.use { out ->
                FileInputStream(temporary).use { it.copyTo(out) }
            }
            LogResult.Success(activity.getString(R.string.log_exported_fmt, displayName(uri) ?: activity.getString(R.string.selected_location)))
        } catch (ex: Exception) {
            LogResult.Failed(activity.getString(R.string.log_export_failed_fmt, ex.message ?: activity.getString(R.string.unknown_error)))
        } finally {
            temporary.delete()
        }
    }

    /** Provider 的显示名称，回退到 URI 的最后一段。 */
    private fun displayName(uri: Uri): String? {
        try {
            activity.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                val column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (column >= 0 && cursor.moveToFirst()) {
                    val name = cursor.getString(column)
                    if (!name.isNullOrEmpty()) return name
                }
            }
        } catch (_: Exception) {
            // 回退到 URI 段。
        }
        val segment = uri.lastPathSegment ?: return null
        return segment.substringAfterLast('/').takeIf { it.isNotEmpty() }
    }
}