package com.gow3.android

import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4

import org.junit.Test
import org.junit.runner.RunWith

import org.junit.Assert.*

/**
 * 仪器化测试，将在 Android 设备上执行。
 *
 * 参见 [testing documentation](http://d.android.com/tools/testing)。
 */
@RunWith(AndroidJUnit4::class)
class ExampleInstrumentedTest {
    @Test
    fun useAppContext() {
        // 被测应用的上下文。
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext
        assertEquals("com.gow3.android", appContext.packageName)
    }
}