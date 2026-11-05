package com.gow3.android.feature.mods

import androidx.compose.foundation.layout.*
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.gow3.android.R
import com.gow3.android.data.Gow3Ini
import com.gow3.android.ui.components.LauncherColors
import com.gow3.android.ui.components.ScreenColumn
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private data class PatchOption(val key: String, val label: Int, val default: String = "0")
private val options = listOf(
    PatchOption("skip_intro", R.string.patch_skip_intro, "1"),
    PatchOption("patch_skip_video", R.string.patch_skip_video, "1"),
    PatchOption("patch_disable_ssao", R.string.patch_ssao),
    PatchOption("patch_disable_motion_blur", R.string.patch_blur),
    PatchOption("patch_disable_dof", R.string.patch_dof),
    PatchOption("patch_disable_bloom", R.string.patch_bloom),
    PatchOption("patch_disable_soft_particles", R.string.patch_particles),
    PatchOption("disable_dynamic_shadows", R.string.param_shadows),
    PatchOption("expand_video_arena", R.string.patch_texture_fix, "1"),
    PatchOption("patch_startup_black_screen", R.string.patch_black_screen, "1"),
)

@Composable
internal fun ModsScreen() {
    val context = LocalContext.current
    val config = remember(context) { File(context.filesDir, "gow3port/gow3.ini") }
    var ini by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var saving by remember { mutableStateOf(false) }
    var failed by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(config) { ini = withContext(Dispatchers.IO) { Gow3Ini.read(config) } }
    ScreenColumn {
        Text(stringResource(R.string.nav_mods), color = LauncherColors.textPrimary,
            fontFamily = FontFamily.Serif, fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Text(stringResource(R.string.patch_next_launch), color = LauncherColors.textMuted, fontSize = 13.sp)
        Text(stringResource(R.string.patch_effect_note), color = LauncherColors.textMuted, fontSize = 12.sp)
        if (failed) Text(stringResource(R.string.patch_save_failed), color = LauncherColors.gold)
        for (option in options) {
            Row(Modifier.fillMaxWidth().padding(vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(option.label), Modifier.weight(1f), color = LauncherColors.textPrimary)
                Switch(checked = (ini[option.key] ?: option.default) == "1", enabled = !saving,
                    onCheckedChange = { enabled ->
                        saving = true
                        scope.launch {
                            val result = withContext(Dispatchers.IO) {
                                runCatching {
                                    check(Gow3Ini.write(config, mapOf(option.key to if (enabled) "1" else "0")))
                                    Gow3Ini.read(config)
                                }
                            }
                            result.onSuccess { ini = it }
                            failed = result.isFailure
                            saving = false
                        }
                    })
            }
        }
        Text(stringResource(R.string.param_desc_expand_video_arena), color = LauncherColors.textMuted, fontSize = 12.sp)
    }
}
