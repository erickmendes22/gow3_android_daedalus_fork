package com.gow3.android.data

import android.content.Context
import java.util.Locale
import ro.cobrabm.fexdroid.SotcPaths

/** Launcher language is separate for Shadow of the Colossus and God of War III. */
internal object LanguageManager {
    const val KEY_LANGUAGE="language"
    const val FOLLOW_SYSTEM="system"
    const val ZH="zh"
    const val EN="en"
    const val PT="pt"

    fun read(context:Context):String {
        val value=context.getSharedPreferences(SotcPaths.prefsName(context),Context.MODE_PRIVATE)
            .getString(KEY_LANGUAGE,FOLLOW_SYSTEM) ?: FOLLOW_SYSTEM
        return if (value in listOf(FOLLOW_SYSTEM,ZH,EN,PT)) value else FOLLOW_SYSTEM
    }
    fun set(context:Context,value:String) {
        if (value !in listOf(FOLLOW_SYSTEM,ZH,EN,PT)) return
        context.getSharedPreferences(SotcPaths.prefsName(context),Context.MODE_PRIVATE)
            .edit().putString(KEY_LANGUAGE,value).apply()
    }
    fun resolve(context:Context):Locale=when(read(context)) {
        PT -> Locale("pt","BR")
        ZH -> Locale.SIMPLIFIED_CHINESE
        EN -> Locale.ENGLISH
        else -> Locale.getDefault()
    }
}
