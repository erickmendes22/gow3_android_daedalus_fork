package com.gow3.android.feature.home

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
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import android.widget.Toast
import com.gow3.android.data.FrameGenStorage
import com.gow3.android.ui.components.LauncherColors

/** Upstream zFitness native bloodframe; off by default, no legacy Vulkan LSFG layer. */
@Composable
internal fun FrameGenerationCard() {
    val context = LocalContext.current
    val storage = remember(context) { FrameGenStorage(context) }
    var selected by remember { mutableIntStateOf(storage.enabledMultiplier()) }
    val dllFound = storage.hasDll()
    fun choose(value: Int) {
        if (storage.setMultiplier(value)) selected = value
        else Toast.makeText(context,
            "Import your Lossless.dll in Settings → General first.", Toast.LENGTH_LONG).show()
    }
    Column(
        modifier = Modifier.fillMaxWidth()
            .background(LauncherColors.surface, RoundedCornerShape(14.dp))
            .border(BorderStroke(1.dp, LauncherColors.gold.copy(alpha = 0.45f)), RoundedCornerShape(14.dp))
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        Text("FRAME GENERATION", color = LauncherColors.gold,
            fontWeight = FontWeight.Bold, fontSize = 12.sp)
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(if (selected >= 2) "Bloodframe ${selected}x" else "Off · original framerate",
                modifier = Modifier.weight(1f), color = LauncherColors.textPrimary, fontSize = 14.sp)
            Switch(checked = selected >= 2, onCheckedChange = {
                choose(if (it) storage.preferredMultiplier() else 0)
            }, enabled = dllFound || selected >= 2)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (multiplier in 2..4) {
                Text("${multiplier}x",
                    modifier = Modifier.weight(1f)
                        .background(if (selected == multiplier) LauncherColors.crimson
                                    else LauncherColors.navSurface, RoundedCornerShape(8.dp))
                        .clickable(enabled = dllFound) { choose(multiplier) }
                        .padding(12.dp),
                    color = if (dllFound) LauncherColors.textPrimary else LauncherColors.textMuted,
                    fontWeight = if (selected == multiplier) FontWeight.Bold else FontWeight.Normal)
            }
        }
        Text(if (dllFound) "Configured for next launch. The in-game drawer can change it live."
             else "Lossless.dll missing · import in Settings → General.",
             color = LauncherColors.textMuted, fontSize = 11.sp)
    }
}
