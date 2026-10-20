package com.gow3.android.feature.home

import android.content.Context
import android.widget.Toast
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.gow3.android.R
import com.gow3.android.data.Gow3Ini
import com.gow3.android.feature.about.LanguageSetting
import com.gow3.android.ui.components.LauncherColors
import com.gow3.android.ui.components.ScreenColumn
import java.io.File

@Composable
internal fun HomeScreen(
    onStartGame: () -> Unit,
    onChooseGameFolder: () -> Unit,
    onChooseUpdateFolder: () -> Unit,
    onInstallBasePkg: () -> Unit,
    onInstallUpdatePkg: () -> Unit,
    pkgInstallBusy: Boolean,
    pkgInstallMessage: String?,
    pkgGeneration: Int,
    onChangeLanguage: (String) -> Unit,
) {
    val context = LocalContext.current
    val isBionic = context.packageName == "com.gow3.android.bionic"
    var iniValues by remember { mutableStateOf(loadIni(context)) }
    var gameDir by remember(pkgGeneration) { mutableStateOf(currentGameDir(context)) }
    var updateDir by remember(pkgGeneration) { mutableStateOf(currentUpdateDir(context)) }

    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                gameDir = currentGameDir(context)
                updateDir = currentUpdateDir(context)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    fun save(key: String, value: String) {
        if (Gow3Ini.write(gow3IniFile(context), mapOf(key to value))) {
            iniValues = iniValues + (key to value)
        } else {
            Toast.makeText(context, context.getString(R.string.settings_save_failed), Toast.LENGTH_SHORT).show()
        }
    }

    var popup by remember { mutableStateOf<HomePopupKind?>(null) }
    fun applyChanges(values: Map<String, String>): Boolean {
        if (!Gow3Ini.write(gow3IniFile(context), values)) return false
        iniValues = iniValues + values
        return true
    }
    ScreenColumn {
        Text(stringResource(R.string.title_god_of_war_iii), color = LauncherColors.textPrimary,
            fontFamily = FontFamily.Serif, fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Text("DAEDALUS · 2.1.7 · ANDROID BIONIC", color = LauncherColors.gold,
            fontSize = 13.sp, fontWeight = FontWeight.Bold)
        Text(gameDir ?: stringResource(R.string.game_folder_not_selected),
            color = LauncherColors.textMuted, fontSize = 12.sp, maxLines = 1)
        HomeSection {
            LaunchButton(onStartGame)
            HomeAction("Selecionar pasta do jogo", onClick = onChooseGameFolder)
            HomeAction("Selecionar atualização", onClick = onChooseUpdateFolder)
            HomeAction("Instalar jogo via PKG", enabled = !pkgInstallBusy, onClick = onInstallBasePkg)
            HomeAction("Instalar atualização via PKG", enabled = !pkgInstallBusy, onClick = onInstallUpdatePkg)
            if (pkgInstallMessage != null)
                Text(pkgInstallMessage, color = LauncherColors.textMuted, fontSize = 12.sp)
        }
        HomeSection("VÍDEO E DESEMPENHO") {
            val fps = iniValues["fps_limit"] ?: "60"
            val vsync = iniValues["vsync"] != "0"
            HomeAction("FPS e VSync · ${if (fps == "0") "Ilimitado" else "$fps FPS"} · ${if (vsync) "VSync ON" else "VSync OFF"}") {
                popup = HomePopupKind.FPS
            }
            HomeAction("Vídeo e resolução · ${iniValues["render_resolution"] ?: "720p"}") {
                popup = HomePopupKind.VIDEO
            }
        }
        HomeSection("MODS E CHEATS") {
            HomeAction("Mods · selecionar e organizar") { popup = HomePopupKind.MODS }
            HomeAction("Cheats · selecionar") { popup = HomePopupKind.CHEATS }
        }
        if (isBionic) {
            FrameGenerationCard()
        }
        Spacer(Modifier.height(12.dp))
    }
    popup?.let { which ->
        HomePopup(which, iniValues, ::applyChanges, close = { popup = null })
    }
}

@Composable
private fun HomeSection(title: String? = null, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth()
        .clip(RoundedCornerShape(20.dp))
        .background(LauncherColors.surface)
        .border(BorderStroke(1.dp, LauncherColors.gold.copy(alpha = 0.55f)), RoundedCornerShape(20.dp))
        .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (title != null) Text(title, color = LauncherColors.gold, fontSize = 15.sp,
            fontWeight = FontWeight.Bold)
        content()
    }
}

@Composable
private fun HomeAction(title: String, enabled: Boolean = true, onClick: () -> Unit) {
    Text(title, Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp))
        .background(LauncherColors.navSurface)
        .border(BorderStroke(1.dp, LauncherColors.gold.copy(alpha = 0.5f)), RoundedCornerShape(16.dp))
        .clickable(enabled = enabled, onClick = onClick)
        .padding(horizontal = 16.dp, vertical = 17.dp),
        color = if (enabled) LauncherColors.textPrimary else LauncherColors.textMuted,
        fontSize = 14.sp)
}

@Composable
private fun PkgAction(label: String, action: () -> Unit, enabled: Boolean, modifier: Modifier = Modifier) {
    Text(
        text = label,
        color = if (enabled) LauncherColors.textPrimary else LauncherColors.textMuted,
        fontSize = 13.sp,
        fontWeight = FontWeight.Bold,
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(LauncherColors.navSurface)
            .border(BorderStroke(1.dp, LauncherColors.gold.copy(alpha = 0.55f)), RoundedCornerShape(10.dp))
            .clickable(enabled = enabled, onClick = action)
            .padding(horizontal = 10.dp, vertical = 15.dp),
    )
}

/** launcher 的 gow3.ini 路径，即游戏、run-gow3.sh 和 GameActivity 读取的同一个文件。 */
private fun gow3IniFile(context: Context): File = File(context.filesDir, "gow3port/gow3.ini")

private fun loadIni(context: Context): Map<String, String> {
    val config = gow3IniFile(context)
    return Gow3Ini.read(java.io.File(config.parentFile, "gow3.default.ini")) + Gow3Ini.read(config)
}

private fun currentGameDir(context: Context): String? =
    context.getSharedPreferences("gow3", Context.MODE_PRIVATE).getString("game_dir", null)

private fun currentUpdateDir(context: Context): String? =
    context.getSharedPreferences("gow3", Context.MODE_PRIVATE).getString("update_dir", null)

@Composable
private fun LaunchButton(onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .height(84.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(Brush.linearGradient(listOf(Color(0xFFB8172B), Color(0xFF8C0D1A), Color(0xFFB8172B))))
            .border(BorderStroke(1.dp, LauncherColors.gold), RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(stringResource(R.string.launch_button), color = LauncherColors.textPrimary, fontFamily = FontFamily.Serif, fontSize = 30.sp, fontWeight = FontWeight.Black, letterSpacing = 1.3.sp)
        Text(stringResource(R.string.start_game_button), color = LauncherColors.textPrimary, fontSize = 10.sp, fontWeight = FontWeight.Medium, letterSpacing = 1.5.sp)
    }
}
