package com.gow3.android.data

import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * 纯日志归档逻辑：将 launcher 运行时的 `logs/` 目录树打包成 `.zip`，条目保留
 * `logs/` 前缀（例如 `logs/android-game.log`）。
 *
 * 保持不依赖 Android，以便宿主端 JVM 测试可以直接验证它，与 [SaveArchive]
 * 思路一致。导出是只读的：日志目录树绝不会被修改、截断或删除，只对打包时
 * 已存在于磁盘上的文件做快照。
 */
internal object LogArchive {

    private const val ROOT = "logs"

    /** 当目录中至少含一个日志文件时为 true。 */
    fun hasLogs(logs: File): Boolean =
        logs.isDirectory && logs.walkTopDown().any { it.isFile }

    /** `yyyyMMdd-HHmmss`，与存档导出使用相同的时间戳格式。 */
    fun stamp(now: Date = Date()): String = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(now)

    /** 将整个 [logs] 目录树写入 [target] 的 zip，条目保留 `logs/` 前缀。 */
    fun pack(logs: File, target: File) {
        val root = logs.parentFile ?: throw IllegalStateException("logs has no parent directory")
        ZipOutputStream(target.outputStream().buffered()).use { zip ->
            logs.walkTopDown().forEach { file ->
                val relative = file.relativeTo(root).invariantSeparatorsPath
                if (file.isDirectory) {
                    zip.putNextEntry(ZipEntry("$relative/"))
                    zip.closeEntry()
                } else {
                    zip.putNextEntry(ZipEntry(relative))
                    file.inputStream().use { it.copyTo(zip) }
                    zip.closeEntry()
                }
            }
        }
    }
}