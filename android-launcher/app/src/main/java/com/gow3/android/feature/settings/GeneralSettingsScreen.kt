package com.gow3.android.feature.settings

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.gow3.android.data.FrameGenStorage
import com.gow3.android.data.SaveManager
import com.gow3.android.data.SaveArchive
import com.gow3.android.data.SaveResult
import com.gow3.android.data.LogManager
import com.gow3.android.data.LogArchive
import com.gow3.android.data.LogResult
import com.gow3.android.feature.about.SaveCard
import com.gow3.android.feature.about.LogCard
import androidx.compose.runtime.DisposableEffect
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.gow3.android.feature.home.GpuDriverCard
import com.gow3.android.feature.about.LanguageSetting
import com.gow3.android.data.Gow3Ini
import com.gow3.android.ui.components.LauncherColors
import com.gow3.android.ui.components.ScreenColumn

@Composable
internal fun GeneralSettingsScreen(saves: SaveManager, logs: LogManager,
    onChangeLanguage: (String) -> Unit) {
    val context = LocalContext.current
    val bionic = context.packageName == "com.gow3.android.bionic"
    var hasSaves by remember { mutableStateOf(SaveArchive.hasSaves(saves.savedataDir())) }
    var hasLogs by remember { mutableStateOf(LogArchive.hasLogs(logs.logsDir())) }
    fun refresh() {
        hasSaves = SaveArchive.hasSaves(saves.savedataDir())
        hasLogs = LogArchive.hasLogs(logs.logsDir())
    }
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) refresh()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    fun showResult(message: String) {
        Toast.makeText(context, message, Toast.LENGTH_LONG).show()
    }
    val storage = remember(context) { FrameGenStorage(context) }
    var dllInstalled by remember { mutableStateOf(storage.hasDll()) }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            val ok = storage.importDll(uri)
            dllInstalled = storage.hasDll()
            Toast.makeText(context, if (ok) "Lossless.dll imported successfully."
                    else "Import failed: select a valid, non-empty Lossless.dll.",
                    Toast.LENGTH_LONG).show()
        }
    }
    ScreenColumn {
        Text("OPÇÕES", color = LauncherColors.textPrimary,
            fontWeight = FontWeight.Bold, fontSize = 22.sp)
        Text("IDIOMA", color = LauncherColors.gold, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        LanguageSetting(onChangeLanguage)
        Text("HUD E CONTROLES", color = LauncherColors.gold, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        val iniFile = remember(context) { java.io.File(context.filesDir, "gow3port/gow3.ini") }
        var ini by remember { mutableStateOf(Gow3Ini.read(iniFile)) }
        androidx.compose.foundation.layout.Row(
            Modifier.fillMaxWidth().background(LauncherColors.surface, RoundedCornerShape(12.dp))
                .border(BorderStroke(1.dp, LauncherColors.gold.copy(alpha = .5f)),
                    RoundedCornerShape(12.dp)).padding(14.dp),
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        ) {
            Text("HUD — FPS / GPU / CPU", Modifier.weight(1f),
                color = LauncherColors.textPrimary, fontSize = 14.sp)
            androidx.compose.material3.Switch(checked = ini["show_fps"] == "1", onCheckedChange = { value ->
                if (Gow3Ini.write(iniFile, mapOf("show_fps" to if (value) "1" else "0")))
                    ini = ini + ("show_fps" to if (value) "1" else "0")
                else showResult("Não foi possível salvar o HUD")
            })
        }
        Text("OPÇÕES", color = LauncherColors.gold, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        GpuDriverCard()
        Text("SALVAMENTOS E LOGS", color = LauncherColors.gold, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        SaveCard(
            hasSaves = hasSaves,
            onExport = {
                saves.launchExport { result ->
                    when (result) {
                        is SaveResult.Success -> showResult(result.message)
                        is SaveResult.Failed -> showResult(result.message)
                        SaveResult.Cancelled -> Unit
                    }
                    refresh()
                }
            },
            onImport = {
                saves.launchImport { result ->
                    when (result) {
                        is SaveResult.Success -> showResult(result.message)
                        is SaveResult.Failed -> showResult(result.message)
                        SaveResult.Cancelled -> Unit
                    }
                    refresh()
                }
            },
        )
        LogCard(hasLogs = hasLogs, onExport = {
            logs.launchExport { result ->
                when (result) {
                    is LogResult.Success -> showResult(result.message)
                    is LogResult.Failed -> showResult(result.message)
                    LogResult.Cancelled -> Unit
                }
                refresh()
            }
        })
        if (bionic) {
            Column(
                modifier = Modifier.fillMaxWidth()
                    .background(LauncherColors.surface, RoundedCornerShape(12.dp))
                    .border(BorderStroke(1.dp, LauncherColors.gold.copy(alpha = 0.5f)),
                            RoundedCornerShape(12.dp))
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text("Lossless.dll · Bloodframe", color = LauncherColors.textPrimary,
                    fontWeight = FontWeight.Bold)
                Text(if (dllInstalled) "Imported · native frame generation is available"
                     else "Not imported · frame generation is disabled by default",
                    color = LauncherColors.textMuted, fontSize = 12.sp)
                Text("IMPORT LOSSLESS.DLL",
                    modifier = Modifier.fillMaxWidth()
                        .background(LauncherColors.crimson, RoundedCornerShape(8.dp))
                        .clickable { importer.launch(arrayOf("*/*")) }
                        .padding(14.dp),
                    color = LauncherColors.textPrimary, fontWeight = FontWeight.Bold)
                Text("The file must be provided by you. Bloodframe uses its shaders; the APK never bundles the DLL.",
                    color = LauncherColors.textMuted, fontSize = 12.sp)
            }
        } else {
            Text("Native Bloodframe options are available in the Bionic version.",
                 color = LauncherColors.textMuted, fontSize = 13.sp)
        }
    }
}
