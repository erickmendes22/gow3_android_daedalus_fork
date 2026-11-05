package com.gow3.android

import com.gow3.android.data.LogArchive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.util.zip.ZipInputStream

class LogArchiveTest {

    private fun tempDir(): File {
        val dir = java.nio.file.Files.createTempDirectory("logarchive-test").toFile()
        dir.deleteOnExit()
        return dir
    }

    private fun makeLogs(root: File): File {
        val logs = File(root, "logs").apply { mkdirs() }
        File(logs, "android-game.log").writeText("Texture integrity: title=CUSA01623\n")
        val nested = File(logs, "turnip").apply { mkdirs() }
        File(nested, "driver.log").writeText("turnip main\n")
        return logs
    }

    private fun zipEntries(zip: File): Map<String, String> {
        val entries = HashMap<String, String>()
        ZipInputStream(zip.inputStream()).use { stream ->
            while (true) {
                val entry = stream.nextEntry ?: break
                if (entry.isDirectory) continue
                entries[entry.name] = stream.readBytes().toString(Charsets.UTF_8)
            }
        }
        return entries
    }

    private fun listFiles(dir: File): Map<String, String> {
        val root = dir.parentFile ?: dir
        return dir.walkTopDown().filter { it.isFile }
            .associate { it.relativeTo(root).invariantSeparatorsPath to it.readText() }
    }

    @Test
    fun `hasLogs is true for a non-empty logs tree`() {
        assertTrue(LogArchive.hasLogs(makeLogs(tempDir())))
    }

    @Test
    fun `hasLogs is false for missing and empty directories`() {
        val dir = tempDir()
        assertFalse(LogArchive.hasLogs(File(dir, "missing")))
        File(dir, "logs").mkdirs()
        assertFalse(LogArchive.hasLogs(File(dir, "logs")))
    }

    @Test
    fun `pack round-trips the logs tree contents`() {
        val dir = tempDir()
        val logs = makeLogs(dir)
        val zip = File(dir, "export.zip")
        LogArchive.pack(logs, zip)
        assertTrue(zip.isFile)
        assertEquals(listFiles(logs), zipEntries(zip))
    }

    @Test
    fun `pack keeps the logs prefix on every entry`() {
        val dir = tempDir()
        val zip = File(dir, "export.zip")
        LogArchive.pack(makeLogs(dir), zip)
        val entries = zipEntries(zip).keys
        assertTrue(entries.contains("logs/android-game.log"))
        assertTrue(entries.contains("logs/turnip/driver.log"))
        assertTrue(entries.all { it.startsWith("logs/") })
    }

    @Test
    fun `pack does not modify the source log files`() {
        val dir = tempDir()
        val logs = makeLogs(dir)
        val before = listFiles(logs)
        LogArchive.pack(logs, File(dir, "export.zip"))
        assertEquals(before, listFiles(logs))
    }

    @Test
    fun `stamp uses the yyyyMMdd-HHmmss layout`() {
        assertTrue(LogArchive.stamp().matches(Regex("""\d{8}-\d{6}""")))
    }
}