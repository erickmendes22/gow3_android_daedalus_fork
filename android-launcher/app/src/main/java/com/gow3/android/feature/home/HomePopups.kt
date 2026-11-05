package com.gow3.android.feature.home

import android.provider.OpenableColumns
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.gow3.android.R
import androidx.compose.ui.res.stringResource
import com.gow3.android.ui.components.LauncherColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.zip.ZipFile

internal enum class HomePopupKind { FPS, VIDEO, CHEATS, MODS }

private val cheats = listOf(
    "cheat_health" to R.string.popup_cheat_health,
    "cheat_magic" to R.string.popup_cheat_magic,
    "cheat_item" to R.string.popup_cheat_item,
    "cheat_rage" to R.string.popup_cheat_rage,
    "cheat_orbs" to R.string.popup_cheat_orbs,
    "cheat_very_hard" to R.string.popup_cheat_very_hard,
    "cheat_double_jumps" to R.string.popup_cheat_double_jumps,
    "auto_qte" to R.string.popup_cheat_auto_qte,
)
private val resolutions = listOf("240p", "360p", "424p", "480p", "540p", "720p",
    "900p", "native", "1440p", "1800p", "4K", "8K")
private val fpsLimits = listOf("30", "60", "120", "240", "0")
private val gsrPresets = listOf(
    "0" to R.string.popup_gsr2_native_aa,
    "1" to R.string.popup_gsr2_quality,
    "2" to R.string.popup_gsr2_balanced,
    "3" to R.string.popup_gsr2_performance,
    "4" to R.string.popup_gsr2_ultra_performance,
)

@Composable
private fun PopupShell(title: String, onDismiss: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    Dialog(onDismissRequest = onDismiss) {
        Column(
            Modifier.fillMaxWidth().heightIn(max = 650.dp)
                .background(LauncherColors.surface, RoundedCornerShape(22.dp))
                .border(BorderStroke(1.dp, LauncherColors.gold), RoundedCornerShape(22.dp))
                .padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(title, color = LauncherColors.textPrimary, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("✕", color = LauncherColors.textMuted,
                    modifier = Modifier.clickable(onClick = onDismiss).padding(horizontal = 8.dp))
            }
            content()
        }
    }
}

@Composable
private fun OptionRow(label: String, checked: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = checked, onClick = onClick)
        Text(label, color = LauncherColors.textPrimary, fontSize = 14.sp)
    }
}

@Composable
private fun PopupAction(label: String, primary: Boolean = false, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Text(
        label,
        color = LauncherColors.textPrimary,
        fontWeight = FontWeight.Bold,
        modifier = modifier
            .background(if (primary) LauncherColors.crimson else LauncherColors.navSurface,
                RoundedCornerShape(12.dp))
            .border(BorderStroke(1.dp, LauncherColors.gold.copy(alpha = 0.8f)),
                RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(12.dp),
    )
}

@Composable
internal fun HomePopup(
    kind: HomePopupKind,
    ini: Map<String, String>,
    apply: (Map<String, String>) -> Boolean,
    close: () -> Unit,
) {
    if (kind == HomePopupKind.MODS) {
        ModsPopup(ini, apply, close)
        return
    }
    var fps by remember(kind) { mutableStateOf(ini["fps_limit"] ?: "60") }
    var engine by remember(kind) { mutableStateOf(ini["engine_fps"] ?: "60") }
    var vsync by remember(kind) { mutableStateOf(ini["vsync"] != "0") }
    var resolution by remember(kind) { mutableStateOf(ini["render_resolution"] ?: "720p") }
    var fullscreen by remember(kind) { mutableStateOf(ini["android_fullscreen"] == "1") }
    val isBionic = LocalContext.current.packageName == "com.gow3.android.bionic"
    var gsr2 by remember(kind) { mutableStateOf(ini["upscaler"] == "gsr2") }
    var gsrPreset by remember(kind) {
        mutableStateOf((ini["preset"] ?: "0").takeIf { it in listOf("0", "1", "2", "3", "4") } ?: "0")
    }
    val enabled = remember(kind) { mutableStateMapOf<String, Boolean>().apply {
        cheats.forEach { (key, _) -> put(key, ini[key] == "1") }
    } }
    val context = LocalContext.current
    val title = when (kind) {
        HomePopupKind.FPS -> stringResource(R.string.popup_fps_title)
        HomePopupKind.VIDEO -> stringResource(R.string.popup_video_title)
        HomePopupKind.CHEATS -> stringResource(R.string.popup_cheats_title)
        HomePopupKind.MODS -> "Mods"
    }
    PopupShell(title, close) {
        Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
            when (kind) {
                HomePopupKind.FPS -> {
                    Text(stringResource(R.string.popup_fps_limit), color = LauncherColors.gold, fontWeight = FontWeight.Bold)
                    fpsLimits.forEach { value ->
                        OptionRow(if (value == "0") stringResource(R.string.popup_unlimited) else "$value FPS", fps == value) {
                            fps = value
                        }
                    }
                    Text(stringResource(R.string.popup_engine_fps), color = LauncherColors.gold, fontWeight = FontWeight.Bold)
                    listOf("60", "120", "240").forEach { value ->
                        OptionRow("$value FPS", engine == value) { engine = value }
                    }
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("VSync", color = LauncherColors.textPrimary)
                        Switch(checked = vsync, onCheckedChange = { vsync = it })
                    }
                }
                HomePopupKind.VIDEO -> {
                    if (isBionic) {
                        Text(stringResource(R.string.popup_gsr2_title), color = LauncherColors.gold,
                            fontWeight = FontWeight.Bold)
                        OptionRow(stringResource(R.string.popup_gsr2_off), !gsr2) { gsr2 = false }
                        OptionRow(stringResource(R.string.popup_gsr2_on), gsr2) {
                            gsr2 = true
                            // Spatial GSR2 never changes the game's resolution.
                        }
                        if (gsr2) {
                            Text(stringResource(R.string.popup_gsr2_spatial_notice),
                                color = LauncherColors.textMuted, fontSize = 12.sp)
                        }
                        Spacer(Modifier.height(10.dp))
                    }
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween) {
                        Column(Modifier.weight(1f)) {
                            Text(stringResource(R.string.settings_fullscreen_title),
                                color = LauncherColors.textPrimary, fontWeight = FontWeight.Bold)
                            Text(stringResource(R.string.settings_fullscreen_desc),
                                color = LauncherColors.textMuted, fontSize = 12.sp)
                        }
                        Switch(checked = fullscreen, onCheckedChange = { fullscreen = it })
                    }
                    Text(stringResource(R.string.popup_internal_resolution), color = LauncherColors.gold,
                        fontWeight = FontWeight.Bold)
                    resolutions.forEach { value ->
                        val label = when (value) {
                            "native" -> stringResource(R.string.popup_native_resolution)
                            "8K" -> stringResource(R.string.popup_8k_resolution)
                            else -> value
                        }
                        // Every resolution remains available with GSR2 spatial.
                        OptionRow(label, resolution == value) { resolution = value }
                    }
                    Text(stringResource(R.string.popup_8k_warning),
                        color = LauncherColors.textMuted, fontSize = 12.sp)
                }
                HomePopupKind.CHEATS -> {
                    Text(stringResource(R.string.popup_cheat_warning),
                        color = LauncherColors.textMuted, fontSize = 12.sp)
                    cheats.forEach { (key, label) ->
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(stringResource(label), Modifier.weight(1f), color = LauncherColors.textPrimary, fontSize = 14.sp)
                            Switch(checked = enabled[key] == true,
                                onCheckedChange = { enabled[key] = it })
                        }
                    }
                }
                HomePopupKind.MODS -> Unit
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            PopupAction(stringResource(R.string.popup_cancel), modifier = Modifier.weight(1f), onClick = close)
            PopupAction(stringResource(R.string.popup_apply), primary = true, modifier = Modifier.weight(1f)) {
                val updates = when (kind) {
                    HomePopupKind.FPS -> mapOf("fps_limit" to fps, "engine_fps" to engine,
                        "vsync" to if (vsync) "1" else "0")
                    HomePopupKind.VIDEO -> if (isBionic) mapOf(
                        "render_resolution" to resolution,
                        "android_fullscreen" to (if (fullscreen) "1" else "0"),
                        "upscaler" to (if (gsr2) "gsr2" else "off"),
                        "preset" to "0", // Spatial filter has no quality presets
                    ) else mapOf("render_resolution" to resolution,
                        "android_fullscreen" to (if (fullscreen) "1" else "0"))
                    HomePopupKind.CHEATS -> enabled.mapValues { if (it.value) "1" else "0" }
                    HomePopupKind.MODS -> emptyMap()
                }
                if (apply(updates)) close()
                else Toast.makeText(context, context.getString(R.string.popup_save_failed), Toast.LENGTH_LONG).show()
            }
        }
    }
}

private fun listModNames(folder: File): List<String> {
    return folder.listFiles()?.asSequence()
        ?.filter { it.isDirectory || (it.isFile && it.extension.equals("zip", ignoreCase = true)) }
        ?.map { if (it.isDirectory) it.name else it.nameWithoutExtension }
        ?.distinct()?.sortedWith(String.CASE_INSENSITIVE_ORDER)?.toList() ?: emptyList()
}

@Composable
private fun ModsPopup(
    ini: Map<String, String>,
    apply: (Map<String, String>) -> Boolean,
    close: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val folder = remember { File(context.filesDir, "gow3port/mods").apply { mkdirs() } }
    val settings = remember { File(context.filesDir, "gow3port/mods.json") }
    var names by remember { mutableStateOf(listModNames(folder)) }
    val original = remember {
        runCatching { JSONObject(settings.readText()) }.getOrElse { JSONObject() }
    }
    val disabled = remember {
        mutableStateListOf<String>().apply {
            val arr = original.optJSONArray("disabled") ?: JSONArray()
            for (i in 0 until arr.length()) add(arr.optString(i))
        }
    }
    val order = remember {
        mutableStateListOf<String>().apply {
            val arr = original.optJSONArray("order") ?: JSONArray()
            for (i in 0 until arr.length()) add(arr.optString(i))
            names.forEach { if (it !in this) add(it) }
        }
    }
    var allEnabled by remember { mutableStateOf(ini["load_mods"] != "0") }
    var importing by remember { mutableStateOf(false) }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null && !importing) {
            importing = true
            scope.launch {
                val outcome = withContext(Dispatchers.IO) {
                    runCatching {
                        val name = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME),
                            null, null, null)?.use { c ->
                            if (c.moveToFirst()) c.getString(0) else null
                        } ?: "mod.zip"
                        require(name.endsWith(".zip", ignoreCase = true)) { context.getString(R.string.popup_mods_select_zip) }
                        val safe = name.substringBeforeLast('.').replace(Regex("[^A-Za-z0-9._-]"), "_")
                            .take(72).trim('.', '_', '-')
                        require(safe.isNotEmpty()) { context.getString(R.string.popup_mods_invalid_name) }
                        val target = File(folder, "$safe.zip")
                        require(!target.exists() && !File(folder, safe).exists()) { context.getString(R.string.popup_mods_exists) }
                        val temp = File(folder, "$safe.zip.part")
                        try {
                            context.contentResolver.openInputStream(uri).use { input ->
                                requireNotNull(input) { context.getString(R.string.popup_mods_unavailable) }
                                temp.outputStream().use { output ->
                                    val buf = ByteArray(64 * 1024)
                                    var total = 0L
                                    while (true) {
                                        val n = input.read(buf)
                                        if (n < 0) break
                                        total += n
                                        require(total <= (16L shl 30)) { context.getString(R.string.popup_mods_too_large) }
                                        output.write(buf, 0, n)
                                    }
                                }
                            }
                            ZipFile(temp).use { zip -> require(zip.size() > 0) { context.getString(R.string.popup_mods_empty_zip) } }
                            check(temp.renameTo(target)) { context.getString(R.string.popup_mods_install_failed) }
                        } finally {
                            temp.delete()
                        }
                        safe
                    }
                }
                importing = false
                outcome.onSuccess {
                    names = listModNames(folder)
                    if (it !in order) order.add(it)
                    Toast.makeText(context, context.getString(R.string.popup_mods_imported_fmt, it), Toast.LENGTH_SHORT).show()
                }.onFailure {
                    Toast.makeText(context, it.message ?: context.getString(R.string.popup_mods_import_failed), Toast.LENGTH_LONG).show()
                }
            }
        }
    }
    PopupShell("Mods · SpartanPort 2.6", close) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.popup_mods_load), color = LauncherColors.textPrimary)
            Switch(checked = allEnabled, onCheckedChange = { allEnabled = it })
        }
        Text(stringResource(R.string.popup_mods_order_help),
            color = LauncherColors.textMuted, fontSize = 12.sp)
        Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
            if (names.isEmpty()) {
                Text(stringResource(R.string.popup_mods_none),
                    color = LauncherColors.textMuted)
            }
            order.filter { it in names }.forEach { mod ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Switch(checked = mod !in disabled && allEnabled, enabled = allEnabled,
                        onCheckedChange = { on -> if (on) disabled.remove(mod) else if (mod !in disabled) disabled.add(mod) })
                    Text(mod, Modifier.weight(1f), color = LauncherColors.textPrimary, fontSize = 13.sp)
                    Text("↑", Modifier.clickable {
                        val idx = order.indexOf(mod)
                        if (idx > 0) { order.removeAt(idx); order.add(idx - 1, mod) }
                    }.padding(9.dp), color = LauncherColors.gold)
                    Text("↓", Modifier.clickable {
                        val idx = order.indexOf(mod)
                        if (idx in 0 until order.lastIndex) { order.removeAt(idx); order.add(idx + 1, mod) }
                    }.padding(9.dp), color = LauncherColors.gold)
                }
            }
        }
        PopupAction(if (importing) stringResource(R.string.popup_mods_importing) else stringResource(R.string.popup_mods_import)) {
            if (!importing) importer.launch(arrayOf("application/zip", "application/octet-stream"))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            PopupAction(stringResource(R.string.popup_cancel), modifier = Modifier.weight(1f), onClick = close)
            PopupAction(stringResource(R.string.popup_apply), primary = true, modifier = Modifier.weight(1f)) {
                val obj = JSONObject().put("order", JSONArray(order)).put("disabled", JSONArray(disabled))
                val success = runCatching {
                    settings.parentFile?.mkdirs()
                    val tmp = File(settings.path + ".tmp")
                    tmp.writeText(obj.toString(2))
                    check(tmp.renameTo(settings))
                    check(apply(mapOf("load_mods" to if (allEnabled) "1" else "0")))
                }.isSuccess
                if (success) close() else Toast.makeText(context, context.getString(R.string.popup_mods_save_failed), Toast.LENGTH_LONG).show()
            }
        }
    }
}
