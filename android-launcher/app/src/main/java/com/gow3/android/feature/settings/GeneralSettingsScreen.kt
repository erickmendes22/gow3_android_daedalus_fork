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
import com.gow3.android.ui.components.LauncherColors
import com.gow3.android.ui.components.ScreenColumn

@Composable
internal fun GeneralSettingsScreen() {
    val context = LocalContext.current
    val bionic = context.packageName == "com.gow3.android.bionic"
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
        Text("Settings", color = LauncherColors.textPrimary,
            fontWeight = FontWeight.Bold, fontSize = 22.sp)
        Text("General", color = LauncherColors.gold, fontSize = 15.sp)
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
