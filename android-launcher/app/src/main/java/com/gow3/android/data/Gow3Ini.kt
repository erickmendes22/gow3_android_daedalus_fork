package com.gow3.android.data

import java.io.File

/**
 * gow3.ini 的安全读写器（key=value 行，`#` 注释），与 Java 前端的
 * SettingsDialog.load()/save() 语义一致：整文件重写，保留其他所有行
 * （注释、空行、未修改的键），在原位替换被修改的键，并在末尾追加缺失的键。
 * 写入先写临时文件再原子重命名，因此失败绝不会破坏原文件。这是 launcher
 * 唯一的启动参数持久化通道；游戏（Gow3Settings::Load）、run-gow3.sh 和
 * 游戏内菜单共享同一文件。
 */
internal object Gow3Ini {

    /** 将 key=value 行解析为映射；`#` 注释和空行被忽略。文件缺失 -> 返回空映射。 */
    fun read(path: File): Map<String, String> {
        if (!path.isFile) return emptyMap()
        val values = LinkedHashMap<String, String>()
        try {
            path.forEachLine { line ->
                val eq = line.indexOf('=')
                if (eq > 0 && !line.startsWith("#")) {
                    values[line.substring(0, eq).trim()] = line.substring(eq + 1).trim()
                }
            }
        } catch (_: Exception) {
            return emptyMap()
        }
        return values
    }

    /**
     * 应用 `updates` 后整体重写 `path`（被修改的键替换其所在行，缺失的键追加到
     * 末尾；其余行原样保留）。成功返回 true；任何失败都会保持原文件不变并返回 false。
     */
    fun write(path: File, updates: Map<String, String>): Boolean {
        val lines = try {
            path.readLines(Charsets.UTF_8)
        } catch (_: Exception) {
            emptyList()
        }
        // Home may save a single option before runtime installation. Once the
        // packaged defaults exist, seed missing keys on every write as well.
        val existing = read(path)
        val pending = LinkedHashMap(read(File(path.parentFile, "gow3.default.ini"))
            .filterKeys { it !in existing })
        pending.putAll(updates)
        val out = mutableListOf<String>()
        for (line in lines) {
            val eq = line.indexOf('=')
            val key = if (eq > 0 && !line.startsWith("#")) line.substring(0, eq).trim() else null
            if (key != null && pending.containsKey(key)) {
                out.add("$key=${pending.remove(key)}")
            } else {
                out.add(line)
            }
        }
        for ((k, v) in pending) out.add("$k=$v")
        val temporary = File(path.path + ".tmp")
        return try {
            temporary.parentFile?.mkdirs()
            temporary.writeText(out.joinToString("\n") + "\n", Charsets.UTF_8)
            if (temporary.renameTo(path)) {
                true
            } else {
                temporary.delete()
                false
            }
        } catch (_: Exception) {
            temporary.delete()
            false
        }
    }
}
