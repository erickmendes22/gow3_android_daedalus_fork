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

    ScreenColumn(horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.height(36.dp))
        Text(stringResource(R.string.title_god_of_war_iii), color = LauncherColors.textPrimary, fontFamily = FontFamily.Serif, fontSize = 20.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.8.sp)
        Text(stringResource(R.string.title_remastered), color = LauncherColors.textMuted, fontSize = 11.sp, fontWeight = FontWeight.Medium, letterSpacing = 2.sp)
        Text(if (isBionic) "Daedalus Fork · Bionic" else "Daedalus Fork", color = LauncherColors.gold, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(28.dp))
        LaunchButton(onStartGame)
        Spacer(Modifier.height(20.dp))
        LaunchParameters(gameDir, updateDir, iniValues, ::save, onChooseGameFolder, onChooseUpdateFolder)
        if (isBionic) {
            FrameGenerationCard()
            Spacer(Modifier.height(12.dp))
        }
        GpuDriverCard()
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            PkgAction(stringResource(R.string.pkg_install), onInstallBasePkg, !pkgInstallBusy, Modifier.weight(1f))
            PkgAction(stringResource(R.string.pkg_update), onInstallUpdatePkg, !pkgInstallBusy, Modifier.weight(1f))
        }
        if (pkgInstallMessage != null) {
            Text(pkgInstallMessage, color = LauncherColors.textMuted, fontSize = 12.sp)
        }
        Spacer(Modifier.height(16.dp))
        LanguageSetting(onChangeLanguage)
        Spacer(Modifier.height(16.dp))
        Spacer(Modifier.height(24.dp))
    }
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
