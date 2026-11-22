package com.gow3.android.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.ImageBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ro.cobrabm.fexdroid.SotcPaths
import com.gow3.android.data.Gow3Ini
import com.gow3.android.data.LogArchive
import com.gow3.android.data.LogManager
import com.gow3.android.data.LogResult
import com.gow3.android.data.SaveArchive
import com.gow3.android.data.SaveManager
import com.gow3.android.data.SaveResult
import com.gow3.android.feature.home.GpuDriverCard
import com.gow3.android.ui.components.ScreenColumn
import java.io.File

// Kept entirely separate from the original God of War III launcher screens.
internal object SotcPalette {
    val text = Color(0xFFEEE9DE)
    val secondary = Color(0xFFAEB9B6)
    val accent = Color(0xFFC6B79A)
    val teal = Color(0xFF4F716C)
    val panel = Color(0xE30C181A)
    val edge = Color(0xFF627B77)
}

@Composable
internal fun SotcBackdrop() {
    Canvas(Modifier.fillMaxSize()) {
        drawRect(Brush.verticalGradient(listOf(Color(0xFF233A3A), Color(0xFF0F1D21), Color(0xFF080F12))))
        val w=size.width
        val h=size.height
        drawCircle(Color(0x44D8D4C1), radius=w*0.19f, center=Offset(w*0.72f,h*0.22f))
        fun ridge(peak:Float,base:Float,color:Color) {
            val p=Path().apply {
                moveTo(0f,h*base)
                lineTo(w*0.14f,h*(peak+0.12f))
                lineTo(w*0.38f,h*peak)
                lineTo(w*0.52f,h*(peak+0.085f))
                lineTo(w*0.70f,h*(peak-0.04f))
                lineTo(w,h*(peak+0.17f))
                lineTo(w,h)
                lineTo(0f,h)
                close()
            }
            drawPath(p,color)
        }
        ridge(0.46f,0.75f,Color(0xB0193030))
        ridge(0.61f,0.90f,Color(0xF0091D20))
        // Distant colossus silhouette: ancient stone body, not artwork from another game.
        val x=w*0.77f
        val y=h*0.61f
        drawRoundRect(Color(0xCD081113),topLeft=Offset(x-w*.055f,y-h*.14f),
            size=Size(w*.115f,h*.25f),cornerRadius=androidx.compose.ui.geometry.CornerRadius(w*.035f))
        drawCircle(Color(0xE4081214),radius=w*.059f,center=Offset(x,y-h*.19f))
        drawLine(Color(0xF2081214),Offset(x-w*.045f,y),Offset(x-w*.075f,y+h*.24f),strokeWidth=w*.04f)
        drawLine(Color(0xF2081214),Offset(x+w*.045f,y),Offset(x+w*.08f,y+h*.24f),strokeWidth=w*.04f)
        drawLine(Color(0xD9081214),Offset(x-w*.047f,y-h*.10f),Offset(x-w*.14f,y+h*.08f),strokeWidth=w*.048f)
        drawLine(Color(0xD9081214),Offset(x+w*.047f,y-h*.10f),Offset(x+w*.14f,y+h*.07f),strokeWidth=w*.048f)
        drawRect(Brush.verticalGradient(listOf(Color.Transparent,Color(0xD8091012))),
            topLeft=Offset(0f,h*.60f),size=Size(w,h*.40f))
    }
}

/**
 * Uses real local artwork from the legally selected PS4 game dump: pic1.png,
 * pic0.png, or icon0.png. No PlayStation game artwork is bundled, scraped or
 * downloaded. Loading happens off the UI thread with a bounded decoder.
 */
@Composable
private fun SotcGameArtwork(gameDir: String?) {
    var bitmap by remember(gameDir) { mutableStateOf<ImageBitmap?>(null) }
    androidx.compose.runtime.LaunchedEffect(gameDir) {
        bitmap = withContext(Dispatchers.IO) {
            if (gameDir.isNullOrBlank()) return@withContext null
            val base=File(gameDir,"sce_sys")
            val artwork=listOf("pic1.png","pic0.png","icon0.png")
                .map { File(base,it) }.firstOrNull { it.isFile && it.canRead() }
                ?: return@withContext null
            try {
                val bounds=BitmapFactory.Options().apply { inJustDecodeBounds=true }
                BitmapFactory.decodeFile(artwork.absolutePath,bounds)
                var sample=1
                while (bounds.outWidth/sample>1536 || bounds.outHeight/sample>1024) sample*=2
                val options=BitmapFactory.Options().apply {
                    inSampleSize=sample
                    inPreferredConfig=android.graphics.Bitmap.Config.RGB_565
                }
                BitmapFactory.decodeFile(artwork.absolutePath,options)?.asImageBitmap()
            } catch (_:Exception) { null }
        }
    }
    Box(Modifier.fillMaxWidth().aspectRatio(1.9f)
        .clip(RoundedCornerShape(15.dp))
        .background(Color(0xFF13272A))) {
        if(bitmap!=null) Image(bitmap=bitmap!!,contentDescription="Shadow of the Colossus",
            modifier=Modifier.fillMaxSize(),contentScale=ContentScale.Crop)
        else Canvas(Modifier.fillMaxSize()) {
            val w=size.width;val h=size.height
            drawRect(Brush.verticalGradient(listOf(Color(0xFF52635C),Color(0xFF243B3F),Color(0xFF121D20))))
            val hills=Path().apply {
                moveTo(0f,h*.78f);lineTo(w*.15f,h*.52f);lineTo(w*.33f,h*.72f)
                lineTo(w*.55f,h*.35f);lineTo(w*.73f,h*.67f)
                lineTo(w,h*.30f);lineTo(w,h);close()
            }
            drawPath(hills,Color(0xC30B1B20))
            // Two silhouettes make the fallback recognisable without pretending
            // a generated vector is a screenshot or a game asset.
            drawRoundRect(Color(0xDD080F11),topLeft=Offset(w*.70f,h*.25f),
                size=Size(w*.10f,h*.50f),
                cornerRadius=androidx.compose.ui.geometry.CornerRadius(w*.025f))
            drawCircle(Color(0xE6081113),w*.075f,Offset(w*.75f,h*.24f))
            drawLine(Color(0xD80A1013),Offset(w*.70f,h*.65f),
                Offset(w*.65f,h*.92f),strokeWidth=w*.045f)
            drawLine(Color(0xD80A1013),Offset(w*.79f,h*.65f),
                Offset(w*.84f,h*.93f),strokeWidth=w*.045f)
            drawCircle(Color(0xFC101919),w*.017f,Offset(w*.28f,h*.72f))
            drawLine(Color(0xF9121C1D),Offset(w*.28f,h*.74f),
                Offset(w*.28f,h*.88f),strokeWidth=w*.02f)
        }
    }
}

private fun localized(context: Context, pt:String, en:String):String =
    if (context.resources.configuration.locales[0].language=="pt") pt else en

@Composable
private fun SotcPanel(content: @Composable ColumnScope.()->Unit) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp))
        .background(SotcPalette.panel)
        .border(BorderStroke(1.dp,SotcPalette.edge.copy(alpha=.65f)),RoundedCornerShape(16.dp))
        .padding(18.dp),verticalArrangement=Arrangement.spacedBy(12.dp),content=content)
}

@Composable
private fun SotcAction(text:String,onClick:()->Unit) {
    SotcAction(text,onClick,Modifier)
}

@Composable
private fun SotcAction(text:String,onClick:()->Unit,modifier:Modifier) {
    Text(text,color=SotcPalette.text,fontWeight=FontWeight.SemiBold,fontSize=13.sp,
        modifier=modifier.clip(RoundedCornerShape(9.dp))
            .background(SotcPalette.teal)
            .clickable(onClick=onClick)
            .padding(horizontal=16.dp,vertical=14.dp))
}

@Composable
private fun SotcChoice(label:String,value:String,options:List<Pair<String,String>>,onChange:(String)->Unit) {
    var expanded by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,verticalAlignment=Alignment.CenterVertically) {
        Text(label,color=SotcPalette.secondary,fontSize=14.sp,modifier=Modifier.weight(1f))
        Box {
            Text((options.firstOrNull {it.first==value}?.second ?: value)+"  ▾",
                color=SotcPalette.text,fontSize=13.sp,
                modifier=Modifier.clip(RoundedCornerShape(9.dp)).background(Color(0xFF273A3B))
                    .clickable { expanded=true }.padding(12.dp))
            DropdownMenu(expanded=expanded,onDismissRequest={expanded=false}) {
                options.forEach { (key,display) ->
                    DropdownMenuItem(text={Text(display)},onClick={expanded=false;onChange(key)})
                }
            }
        }
    }
}

@Composable
private fun SotcToggle(label:String,checked:Boolean,onChange:(Boolean)->Unit) {
    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.SpaceBetween) {
        Text(label,color=SotcPalette.text,fontSize=14.sp,modifier=Modifier.weight(1f))
        Switch(checked=checked,onCheckedChange=onChange)
    }
}

@Composable
internal fun SotcScreen(tabIndex:Int,onStartGame:()->Unit,onChooseGameFolder:()->Unit,
    onChooseUpdateFolder:()->Unit,onInstallBasePkg:()->Unit,onInstallUpdatePkg:()->Unit,
    pkgInstallBusy:Boolean,pkgInstallMessage:String?,pkgGeneration:Int,
    saves:SaveManager,logs:LogManager,onChangeLanguage:(String)->Unit,
    onBuildAot:()->Unit,aotBusy:Boolean,aotMessage:String?
) {
    val ctx=LocalContext.current
    val config=remember { File(ctx.filesDir,"sotcport/sotc.ini") }
    var values by remember { mutableStateOf(Gow3Ini.read(config)) }
    var gameDir by remember(pkgGeneration) { mutableStateOf(
        ctx.getSharedPreferences(SotcPaths.prefsName(ctx),Context.MODE_PRIVATE).getString("game_dir",null)) }
    // Reopening a tab refreshes the selected game folder after a SAF picker.
    androidx.compose.runtime.LaunchedEffect(tabIndex,pkgGeneration) {
        gameDir=ctx.getSharedPreferences(SotcPaths.prefsName(ctx),Context.MODE_PRIVATE).getString("game_dir",null)
        values=Gow3Ini.read(config)
    }
    fun save(key:String,value:String) {
        if (Gow3Ini.write(config,mapOf(key to value))) values=values+(key to value)
        else Toast.makeText(ctx,localized(ctx,"Não foi possível salvar.","Could not save setting."),Toast.LENGTH_SHORT).show()
    }
    val prefs=ctx.getSharedPreferences(SotcPaths.prefsName(ctx),Context.MODE_PRIVATE)
    var autoStart by remember { mutableStateOf(prefs.getBoolean("sotc_auto_start",false)) }
    val launcherLanguage=prefs.getString("language","system") ?: "system"
    val pt=ctx.resources.configuration.locales[0].language=="pt"
    ScreenColumn {
        when(tabIndex) {
            0 -> {
                Spacer(Modifier.height(12.dp))
                Text("SHADOW OF THE COLOSSUS",color=SotcPalette.text,
                    fontSize=26.sp,fontFamily=FontFamily.Serif,fontWeight=FontWeight.Bold)
                Text("DAEDALUS  •  ARM64 AOT NATIVO",color=SotcPalette.accent,
                    fontSize=12.sp,letterSpacing=1.sp)
                Text(if(pt) "Port experimental baseado no projeto de PC de AjncSystem."
                     else "Experimental port based on AjncSystem's PC project.",
                    color=SotcPalette.secondary,fontSize=12.sp)
                Spacer(Modifier.height(12.dp))
                SotcGameArtwork(gameDir)
                Spacer(Modifier.height(8.dp))
                SotcAction(if(pt) "INICIAR SHADOW OF THE COLOSSUS" else "START SHADOW OF THE COLOSSUS",onStartGame,
                    Modifier.fillMaxWidth())
                SotcPanel {
                    SotcToggle(if(pt) "Entrar direto no jogo nas próximas vezes" else "Enter game automatically next time",
                        autoStart,{ checked ->
                            autoStart=checked
                            prefs.edit().putBoolean("sotc_auto_start",checked).apply()
                        })
                    Text(if(pt) "IDIOMA DO LAUNCHER" else "LAUNCHER LANGUAGE",
                        color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    SotcChoice(if(pt) "Interface" else "Interface",
                        launcherLanguage,listOf("system" to (if(pt) "Sistema" else "System"),
                            "pt" to "Português (Brasil)","en" to "English"),onChangeLanguage)
                    Text(if(pt) "IDIOMA DO JOGO" else "GAME LANGUAGE",
                        color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    SotcChoice(if(pt) "Vozes e textos" else "Voices and text",
                        values["sotc_game_language"]?:"system",
                        listOf("system" to (if(pt) "Seguir dispositivo" else "Follow device"),
                            "1" to "English (US)",
                            "7" to "Português (Portugal)",
                            "17" to "Português (Brasil)",
                            "3" to "Español",
                            "2" to "Français",
                            "4" to "Deutsch",
                            "5" to "Italiano"),
                        {save("sotc_game_language",it)})
                    Text(if(pt) "O jogo precisa oferecer o idioma selecionado. A troca é aplicada no próximo início, sem recompilar."
                         else "The selected language must exist in the game. Changes apply on next launch without AOT recompilation.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                }
                SotcPanel {
                    Text(if(pt) "JOGO" else "GAME",color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    Text(gameDir ?: (if(pt) "Pasta não selecionada" else "Game folder not selected"),
                        color=SotcPalette.text,fontSize=12.sp,maxLines=2)
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        SotcAction(if(pt) "Escolher pasta" else "Choose folder",onChooseGameFolder)
                        SotcAction(if(pt) "Atualização" else "Update folder",onChooseUpdateFolder)
                    }
                    Text(if(pt) "Suporta CUSA08809 (EU 1.01) e CUSA08034 (US 1.00)."
                        else "Supports CUSA08809 (EU 1.01) and CUSA08034 (US 1.00).",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        SotcAction(if(pt) "Instalar PKG" else "Install PKG",onInstallBasePkg,
                            Modifier.weight(1f))
                        SotcAction(if(pt) "PKG update" else "Update PKG",onInstallUpdatePkg,
                            Modifier.weight(1f))
                    }
                    if(pkgInstallBusy) Text(if(pt) "Instalando…" else "Installing…",color=SotcPalette.secondary)
                    if(pkgInstallMessage!=null) Text(pkgInstallMessage,color=SotcPalette.secondary,fontSize=12.sp)
                }
                SotcPanel {
                    Text(if(pt) "CÓDIGO NATIVO ARM64" else "NATIVE ARM64 CODE",
                        color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    Text(if(pt)
                        "No primeiro início o jogo é compilado obrigatoriamente no aparelho. Ao mudar os patches, o AOT é verificado e recompilado automaticamente somente quando necessário. Perfis já compilados são reutilizados."
                        else "On first play the game is compiled on the device. Patch changes trigger automatic verification and compilation only if necessary; previously compiled profiles are reused.",
                        color=SotcPalette.secondary,fontSize=12.sp)
                    if(aotBusy) {
                        Text(if(pt) "Preparando jogo (AOT obrigatório)…" else "Preparing game (required AOT)…",
                            color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    }
                    if(aotMessage!=null) Text(aotMessage,color=SotcPalette.text,fontSize=12.sp)
                }
                GpuDriverCard()
            }
            1 -> {
                Text(if(pt) "PATCHES DO JOGO" else "GAME PATCHES",color=SotcPalette.text,
                    fontSize=23.sp,fontFamily=FontFamily.Serif,fontWeight=FontWeight.Bold)
                Text(if(pt)
                    "As mudanças são salvas automaticamente. Ao iniciar, o AOT verifica os novos patches e recompila apenas se não houver um perfil compatível já pronto."
                    else "Changes are saved automatically. On Play, AOT verifies the new patches and compiles only if no matching profile is available.",
                    color=SotcPalette.secondary,fontSize=12.sp)
                SotcPanel {
                    SotcToggle(if(pt) "Desativar Bloom" else "Disable Bloom",
                        (values["sotc_bachata_bloom"]?:"1")=="1",
                        {save("sotc_bachata_bloom",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Desativar Motion Blur" else "Disable Motion Blur",
                        (values["sotc_blur_suppression"]?:"1")=="1",
                        {save("sotc_blur_suppression",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Desativar reflexos SSR" else "Disable SSR reflections",
                        (values["sotc_bachata_ssr"]?:"0")=="1",
                        {save("sotc_bachata_ssr",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Desativar névoa" else "Disable fog",
                        (values["sotc_bachata_fog"]?:"0")=="1",
                        {save("sotc_bachata_fog",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Desativar sombras dinâmicas" else "Disable dynamic shadows",
                        (values["sotc_bachata_shadows"]?:"0")=="1",
                        {save("sotc_bachata_shadows",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Filtragem anisotrópica 16×" else "16× anisotropic filtering",
                        (values["sotc_af16"]?:"0")=="1",
                        {save("sotc_af16",if(it)"1" else "0")})
                    Text(if(pt)
                        "Patches de eboot verificados por hash para CUSA08809. A cópia original e os saves permanecem intactos. O teste de sombras solares foi removido."
                        else "Hash-verified eboot patches for CUSA08809. Original game and saves remain untouched. The ineffective sun-shadow experiment was removed.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                }
                if(aotBusy) Text(aotMessage ?: "AOT ARM64…",
                    color=SotcPalette.accent,fontSize=12.sp)
            }
            else -> {
                Text("SHADOW OF THE COLOSSUS",color=SotcPalette.text,
                    fontFamily=FontFamily.Serif,fontWeight=FontWeight.Bold,fontSize=23.sp)
                Text(if(pt) "DAEDALUS • ARM64 AOT NATIVO" else "DAEDALUS • NATIVE ARM64 AOT",color=SotcPalette.accent,fontSize=13.sp)
                SotcPanel {
                    Text(if(pt) "PORT ANDROID" else "ANDROID PORT",color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    Text(if(pt) "Port Android com renderizador Vulkan e recompilação ARM64 nativa no celular."
                         else "Android port with Vulkan rendering and native ARM64 compilation on-device.",
                         color=SotcPalette.secondary,fontSize=13.sp)
                    Text("Original PC port: AjncSystem/ShadowOfTheColossus-PC",color=SotcPalette.text,fontSize=13.sp)
                    SotcAction(if(pt) "Projeto original" else "Original project") {
                        ctx.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse("https://github.com/AjncSystem/ShadowOfTheColossus-PC")))
                    }
                    Text("Android / Daedalus: erickmendes22",color=SotcPalette.text,fontSize=13.sp)
                    Text("YouTube: @daedalusemulator",color=SotcPalette.secondary)
                    SotcAction("GitHub") {
                        ctx.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse("https://github.com/erickmendes22/gow3_android_daedalus_fork/tree/sotc-apk-integration")))
                    }
                }
                SotcPanel {
                    Text(if(pt) "DIAGNÓSTICO" else "DIAGNOSTICS",color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    SotcAction(if(pt) "Exportar logs" else "Export logs") {
                        logs.launchExport { outcome ->
                            if(outcome is LogResult.Failed) Toast.makeText(ctx,outcome.message,Toast.LENGTH_LONG).show()
                        }
                    }
                }
                SotcPanel {
                    Text(if(pt) "SAVES" else "SAVE DATA",color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
                        SotcAction(if(pt) "Exportar" else "Export") { saves.launchExport { } }
                        SotcAction(if(pt) "Importar" else "Import") { saves.launchImport { } }
                    }
                }
                SotcPanel {
                    Text(if(pt) "IDIOMA" else "LANGUAGE",color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                        SotcAction("Português") { onChangeLanguage("pt") }
                        SotcAction("English") { onChangeLanguage("en") }
                    }
                }
            }
        }
        Spacer(Modifier.height(30.dp))
    }
}
