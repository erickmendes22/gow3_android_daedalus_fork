package com.gow3.android.data

import android.content.Context
import java.util.Locale

/**
 * 启动器语言设置：跟随系统 / 简体中文 / English。
 *
 * 读 `SharedPreferences`（`gow3` key `language`）得到覆盖值（`system`/`zh`/`en`），
 * 再解析出应注入 Activity 的 `Locale`。`system` 表示跟随设备系统语言，其余为固定
 * 覆盖。`MainActivity.attachBaseContext` 与 About 页语言入口都依赖它。
 */
internal object LanguageManager {
    const val PREF_NAME = "gow3"
    const val KEY_LANGUAGE = "language"
    const val FOLLOW_SYSTEM = "system"
    const val ZH = "zh"
    const val EN = "en"
    const val PT = "pt"

    /** 读取持久化的语言覆盖值；未设置时返回 [FOLLOW_SYSTEM]。 */
    fun read(context: Context): String =
        if (context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
                .getString(KEY_LANGUAGE, EN) == PT) PT else EN

    /** 持久化语言覆盖值。 */
    fun set(context: Context, value: String) {
        context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
            .edit().putString(KEY_LANGUAGE, value).apply()
    }

    /** 解析当前生效的 Locale：`system` 跟随设备系统语言，其余为固定覆盖。 */
    fun resolve(context: Context): Locale = when (read(context)) {
        PT -> Locale("pt", "BR")
        else -> Locale.ENGLISH
    }
}
