package com.gow3.android.feature.home

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.gow3.android.R
import com.gow3.android.ui.components.LauncherColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import ro.cobrabm.fexdroid.GpuDriverManager

@Composable
internal fun GpuDriverCard() {
    val context = LocalContext.current
    if (!GpuDriverManager.supported(context)) return
    val scope = rememberCoroutineScope()
    var installed by remember { mutableStateOf(GpuDriverManager.installed(context)) }
    var selected by remember { mutableStateOf(GpuDriverManager.selected(context)) }
    var expanded by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val choices = listOf(
        "auto" to (stringResource(R.string.gpu_driver_auto) + " · " + GpuDriverManager.automaticDescription(context)),
        "system" to stringResource(R.string.gpu_driver_system),
        "gen8" to stringResource(R.string.gpu_driver_bundled),
        "adreno7xx" to stringResource(R.string.gpu_driver_adreno7xx),
    ) + (if (GpuDriverManager.maliCandidate() && android.os.Build.VERSION.SDK_INT >= 35)
        listOf("panvk" to "PanVK 3.2 (Mali, experimental)")
        else emptyList()) + installed.map { "custom:${it.id}" to "${it.name} (${it.id.take(8)})" }
    val label = choices.firstOrNull { it.first == selected }?.second
        ?: stringResource(R.string.gpu_driver_missing)
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            busy = true
            scope.launch {
                try {
                    withContext(Dispatchers.IO) { GpuDriverManager.importDriver(context, uri) }
                    installed = GpuDriverManager.installed(context)
                    selected = GpuDriverManager.selected(context)
                } catch (ex: Exception) {
                    error = GpuDriverManager.error(context, ex)
                } finally { busy = false }
            }
        }
    }
    Column(
        modifier = Modifier.padding(top = 12.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp))
            .background(LauncherColors.surface)
            .border(BorderStroke(1.dp, LauncherColors.gold.copy(alpha = 0.5f)), RoundedCornerShape(14.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(stringResource(R.string.gpu_driver_title), color = LauncherColors.gold,
            fontFamily = FontFamily.Serif, fontSize = 11.sp, fontWeight = FontWeight.Bold)
        Column {
            Text(label, color = LauncherColors.textPrimary, fontSize = 14.sp,
                modifier = Modifier.fillMaxWidth().clickable(enabled = !busy) { expanded = true }.padding(vertical = 8.dp))
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                choices.forEach { (value, name) ->
                    DropdownMenuItem(text = { Text(if (value == selected) "✓ $name" else name) }, onClick = {
                        expanded = false
                        try { GpuDriverManager.select(context, value); selected = value }
                        catch (ex: Exception) { error = GpuDriverManager.error(context, ex) }
                    })
                }
            }
        }
        Text(stringResource(R.string.gpu_driver_hint), color = LauncherColors.textMuted, fontSize = 12.sp)
        Text(stringResource(R.string.gpu_driver_mali_notice),
            color = LauncherColors.gold, fontSize = 12.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(enabled = !busy, onClick = {
                try { picker.launch(arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream")) }
                catch (ex: Exception) { error = GpuDriverManager.error(context, ex) }
            }) { Text(stringResource(if (busy) R.string.gpu_driver_importing else R.string.gpu_driver_import), color = LauncherColors.gold) }
        }
    }
    if (error != null) {
        AlertDialog(onDismissRequest = { error = null },
            title = { Text(stringResource(R.string.gpu_driver_error)) },
            text = { Text(error.orEmpty()) },
            confirmButton = { TextButton(onClick = { error = null }) { Text(stringResource(android.R.string.ok)) } })
    }
}
