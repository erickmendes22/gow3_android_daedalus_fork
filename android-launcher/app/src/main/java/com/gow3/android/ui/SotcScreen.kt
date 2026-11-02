package com.gow3.android.ui

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
    saves:SaveManager,logs:LogManager,onChangeLanguage:(String)->Unit
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
    val pt=ctx.resources.configuration.locales[0].language=="pt"
    ScreenColumn {
        when(tabIndex) {
            0 -> {
                Spacer(Modifier.height(12.dp))
                Text("SHADOW OF THE COLOSSUS",color=SotcPalette.text,
                    fontSize=26.sp,fontFamily=FontFamily.Serif,fontWeight=FontWeight.Bold)
                Text("DAEDALUS  •  ANDROID BIONIC / FEX",color=SotcPalette.accent,
                    fontSize=12.sp,letterSpacing=1.sp)
                Text(if(pt) "Port experimental baseado no projeto de PC de AjncSystem."
                     else "Experimental port based on AjncSystem's PC project.",
                    color=SotcPalette.secondary,fontSize=12.sp)
                Spacer(Modifier.height(12.dp))
                SotcAction(if(pt) "INICIAR SHADOW OF THE COLOSSUS" else "START SHADOW OF THE COLOSSUS",onStartGame,
                    Modifier.fillMaxWidth())
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
                    Text(if(pt) "VÍDEO E DESEMPENHO" else "VIDEO & PERFORMANCE",
                        color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    SotcChoice(if(pt) "Resolução interna" else "Internal resolution",
                        values["sotc_resolution"]?:"720p",
                        listOf("360p" to "640×360","540p" to "960×540",
                            "720p" to "1280×720","900p" to "1600×900",
                            "1080p" to "1920×1080"),{save("sotc_resolution",it)})
                    Text(if(pt) "A resolução escolhida é aplicada aos render targets do jogo na próxima inicialização; a saída Android continua em 720p para ampliar a imagem. Para 360p/540p, confira a resolução efetiva no log."
                         else "This changes the game's render targets on next launch; Android output stays at 720p and upscales the image. Check the effective 360p/540p render size in logs.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcChoice(if(pt) "Modo de FPS" else "FPS mode",
                        values["sotc_fps_mode"]?:"fps60game",
                        listOf("30" to (if(pt) "30 FPS (original)" else "30 FPS (original)"),
                            "fps60game" to "60 FPS (game mode)",
                            "fps60" to "60 FPS (patch)"),{save("sotc_fps_mode",it)})
                    SotcToggle("VSync",(values["sotc_vsync"]?:"1")=="1",
                        {save("sotc_vsync",if(it)"1" else "0")})
                    SotcChoice(if(pt) "Readback da GPU" else "GPU readback mode",
                        values["sotc_readbacks"]?:"2",
                        listOf("0" to (if(pt) "0 — Desativado" else "0 — Disabled"),
                            "1" to (if(pt) "1 — Relaxado" else "1 — Relaxed"),
                            "2" to (if(pt) "2 — Preciso" else "2 — Precise")),
                        {save("sotc_readbacks",it)})
                    Text(if(pt) "2 (padrão) é preciso. 1 pode causar dados e imagens desatualizados; 0 desativa os readbacks e pode quebrar a renderização. Reinicie o jogo após alterar."
                         else "2 (default) is precise. 1 may cause stale GPU data/images; 0 disables readbacks and may break rendering. Restart the game after changing.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "Adreno: compatibilidade Wave32" else "Adreno: Wave32 compatibility",
                        (values["sotc_adreno_wave32"]?:"0")=="1",
                        {save("sotc_adreno_wave32",if(it)"1" else "0")})
                    Text(if(pt) "Experimental. Usa cache de shaders separado; reinicie o jogo para comparar Wave32 e Wave64."
                         else "Experimental. Uses a separate shader cache; restart to compare Wave32 and Wave64.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "HUD de FPS" else "FPS HUD",
                        (values["sotc_show_fps"]?:"1")=="1",
                        {save("sotc_show_fps",if(it)"1" else "0")})
                }
                GpuDriverCard()
            }
            1 -> {
                Text(if(pt) "PATCHES DO SOTC" else "SOTC PATCHES",color=SotcPalette.text,
                    fontSize=23.sp,fontFamily=FontFamily.Serif,fontWeight=FontWeight.Bold)
                Text(if(pt) "Opções específicas do Shadow of the Colossus. Aplicadas no próximo início."
                    else "Shadow of the Colossus-specific options. Applied at the next launch.",
                    color=SotcPalette.secondary,fontSize=12.sp)
                SotcPanel {
                    SotcToggle(if(pt) "Filtragem anisotrópica 16×" else "16× anisotropic filtering",
                        (values["sotc_af16"]?:"0")=="1",{save("sotc_af16",if(it)"1" else "0")})
                    Text(if(pt) "BACHATA S4+ 0.2.7 — PERFORMANCE" else "BACHATA S4+ 0.2.7 — PERFORMANCE",
                        color=SotcPalette.accent,fontWeight=FontWeight.Bold,fontSize=12.sp)
                    SotcToggle(if(pt) "Desativar Bloom" else "Disable Bloom",
                        (values["sotc_bachata_bloom"]?:"1")=="1",
                        {save("sotc_bachata_bloom",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Desativar reflexos SSR" else "Disable screen-space reflections",
                        (values["sotc_bachata_ssr"]?:"0")=="1",
                        {save("sotc_bachata_ssr",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Desativar névoa volumétrica" else "Disable fog",
                        (values["sotc_bachata_fog"]?:"0")=="1",
                        {save("sotc_bachata_fog",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Desativar sombras dinâmicas (experimental)" else "Disable dynamic shadows (experimental)",
                        (values["sotc_bachata_shadows"]?:"0")=="1",
                        {save("sotc_bachata_shadows",if(it)"1" else "0")})
                    Text(if(pt) "Patches no eboot CUSA08809 original com bytes e hash validados. Bloom e Motion Blur desligados por padrão; outros opcionais. Reinicie o jogo."
                         else "Original CUSA08809 eboot patches with validated bytes and SHA256. Bloom and Motion Blur off by default; other effects optional. Restart the game.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "Desativar Motion Blur" else "Disable Motion Blur",
                        (values["sotc_blur_suppression"]?:"1")=="1",
                        {save("sotc_blur_suppression",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Compilação assíncrona de shaders (experimental)"
                                      else "Asynchronous shader compilation (experimental)",
                        (values["sotc_async_shaders"]?:"0")=="1",
                        {save("sotc_async_shaders",if(it)"1" else "0")})
                    Text(if(pt) "OFF por padrão. Compila pipelines gráficos em paralelo, mas pode causar objetos ausentes ou piscadas enquanto compila. Desative e reinicie para restaurar a renderização completa. Não altera readback, thread Vulkan nem FAST_BIND."
                         else "OFF by default. Builds graphics pipelines in parallel, but may cause missing geometry or flicker while compiling. Turn OFF and restart to restore complete rendering. Does not change readback, Vulkan thread, or FAST_BIND.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "Compilação assíncrona compute (experimental)"
                                      else "Asynchronous compute pipeline compilation (experimental)",
                        (values["sotc_async_compute"]?:"0")=="1",
                        {save("sotc_async_compute",if(it)"1" else "0")})
                    Text(if(pt) "OFF por padrão. Só atua com shaders assíncronos e thread Vulkan ligados. Preserva a espera pelos resultados compute; pode aumentar uso de CPU."
                         else "OFF by default. Requires asynchronous shaders and Vulkan recording thread. Compute results remain synchronized; may raise CPU load.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "Blit de tela cheia sem limpeza redundante"
                                      else "Skip redundant fullscreen blit clear",
                        (values["sotc_present_full_blit"]?:"1")=="1",
                        {save("sotc_present_full_blit",if(it)"1" else "0")})
                    Text(if(pt) "Mantém limpeza e barreiras quando a imagem não preenche toda a tela. Reinicie para aplicar."
                         else "Preserves clearing and barriers for any partial or letterboxed blit. Restart to apply.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "Diagnóstico real de gargalo CPU/GPU (log)"
                                      else "CPU/GPU frame bottleneck profiling (log)",
                        (values["sotc_perf_profile"]?:"0")=="1",
                        {save("sotc_perf_profile",if(it)"1" else "0")})
                    Text(if(pt) "Desligado por padrão. A cada 5 s registra CPU real das threads de desenho/processamento, tempo em binds, readback, esperas GPU, texturas e comandos. A medição tem custo: desligue ao comparar FPS e reinicie para aplicar."
                         else "OFF by default. Logs real draw/command CPU time, binds, readbacks, GPU waits, textures and command costs every 5 s. Profiling has overhead: disable for FPS comparisons and restart to apply.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "Reuso exato de especializações FS/CS (CPU)"
                                      else "Exact FS/CS shader specialization reuse (CPU)",
                        (values["sotc_stage_spec_memo"]?:"1")=="1",
                        {save("sotc_stage_spec_memo",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Transferir dados SRT sem copiar (CPU)"
                                      else "Zero-copy CP-to-draw SRT snapshot (CPU)",
                        (values["sotc_stage_snapshot_swap"]?:"1")=="1",
                        {save("sotc_stage_snapshot_swap",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Evitar registrar blocos de registradores iguais (CPU)"
                                      else "Skip unchanged GPU register snapshots (CPU)",
                        (values["sotc_reg_snapshot_memo"]?:"1")=="1",
                        {save("sotc_reg_snapshot_memo",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Reutilização conservadora de render targets (teste)"
                                      else "Conservative render-state memo (test)",
                        (values["sotc_rt_memo"]?:"1")=="1",
                        {save("sotc_rt_memo",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Cache seguro de regiões de memória (CPU)"
                                      else "Safe guest-memory region cache (CPU)",
                        (values["sotc_vm_range_cache"]?:"1")=="1",
                        {save("sotc_vm_range_cache",if(it)"1" else "0")})
                    Text(if(pt) "O cache de regiões evita consultas repetidas ao lock da memória enquanto os mapeamentos continuarem válidos. Não modifica texturas, readback ou shaders. OFF restaura o cache anterior; reinicie após alterar."
                         else "Region cache avoids repeated guest-memory locks while mappings remain valid. Does not change textures, readbacks, or shaders. OFF restores the previous cache; restart to apply.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    Text(if(pt) "Ambas ligadas por padrão. O reuso só ocorre se os dados reais do shader forem idênticos; a transferência preserva os dados de cada draw. Desative individualmente para comparar com o 0.1.29 e reinicie."
                         else "Both ON by default. Reuse requires exactly matching live shader data; the transfer preserves each draw's snapshot. Turn either OFF to compare with 0.1.29, then restart.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "Cache de bind Vulkan (sem pular draws)" else "Vulkan pipeline bind cache (no skipped draws)",
                        (values["sotc_pipeline_bind_memo"]?:"1")=="1",
                        {save("sotc_pipeline_bind_memo",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Cache de atributos Vertex Input" else "Vertex Input state cache",
                        (values["sotc_vertex_input_memo"]?:"1")=="1",
                        {save("sotc_vertex_input_memo",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Reutilizar estruturas de descritores Vulkan" else "Reuse Vulkan descriptor write slots",
                        (values["sotc_descriptor_slot_reuse"]?:"1")=="1",
                        {save("sotc_descriptor_slot_reuse",if(it)"1" else "0")})
                    Text(if(pt) "Otimizações de CPU no renderer: ativas por padrão, não desativam materiais ou sincronização. Reinicie após alterar."
                         else "Renderer CPU optimizations default ON and do not disable materials or synchronization. Restart after changes.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "Reutilização rápida de descritores GPU (teste)" else "GPU fast descriptor reuse (test)",
                        (values["sotc_fast_bind"]?:"0")=="1",
                        {save("sotc_fast_bind",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Thread separada de comandos Vulkan (teste)" else "Separate Vulkan recording thread (test)",
                        (values["sotc_record_thread"]?:"0")=="1",
                        {save("sotc_record_thread",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Readback assíncrono da GPU (teste)" else "Asynchronous GPU readback (test)",
                        (values["sotc_rb_async"]?:"0")=="1",
                        {save("sotc_rb_async",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Agrupar readbacks sequenciais da GPU" else "Batch sequential GPU readbacks",
                        (values["sotc_rb_stream"]?:"1")=="1",
                        {save("sotc_rb_stream",if(it)"1" else "0")})
                    Text(if(pt) "Readback preciso 2: antecipa páginas ainda modificadas pela GPU em janelas de até 512 KiB para diminuir esperas repetidas. Desligue para o comportamento da 0.1.32. Reinicie."
                         else "Precise readback 2: prefetches GPU-modified pages in windows up to 512 KiB to reduce sequential waits. Disable to restore 0.1.32 behavior. Restart.",
                         color=SotcPalette.secondary,fontSize=11.sp)
                    Text(if(pt) "Teste A/B: gravação Vulkan e readback assíncrono independentes e desligados por padrão. Ative um de cada vez; Readbacks 2 permanece ativo. Reinicie a cada mudança."
                         else "A/B test: Vulkan recording and async readback are independent and default OFF. Enable one at a time; required readbacks remain mode 2. Restart after changing.",
                         color=SotcPalette.secondary,fontSize=11.sp)
                    Text(if(pt) "LABORATÓRIO DE DESEMPENHO — SOTC" else "SOTC PERFORMANCE LAB",
                        color=SotcPalette.text,fontWeight=FontWeight.Bold,fontSize=17.sp)
                    Text(if(pt) "26 controles independentes. Altere um de cada vez e reinicie o jogo. Os valores padrão mantêm o desempenho da 0.1.34."
                         else "26 individual controls. Change one at a time and restart. Defaults retain 0.1.34 performance.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    Text(if(pt) "READBACK E SUBMISSÃO VULKAN" else "GPU READBACK AND SUBMISSION",
                        color=SotcPalette.accent,fontWeight=FontWeight.Bold,fontSize=12.sp)
                    SotcToggle(if(pt) "Readback antecipado independente (experimental)" else "Ahead-of-queue GPU readback (experimental)",
                        (values["sotc_rb_ahead"]?:"0")=="1",
                        {save("sotc_rb_ahead",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Enviar comandos antes dos readbacks" else "Submit GPU commands before readbacks",
                        (values["sotc_rb_early"]?:"1")=="1",
                        {save("sotc_rb_early",if(it)"1" else "0")})
                    SotcChoice(if(pt) "Janela básica de readback" else "Base readback window",
                        values["sotc_rb_narrow"]?:"64",
                        listOf("0" to "512 KiB (original)", "64" to "64 KiB", "128" to "128 KiB", "256" to "256 KiB", "512" to "512 KiB"),
                        {save("sotc_rb_narrow",it)})
                    SotcChoice(if(pt) "Janela máxima de readback sequencial" else "Max sequential readback",
                        values["sotc_rb_stream_max_kb"]?:"512",
                        listOf("128" to "128 KiB", "256" to "256 KiB", "512" to "512 KiB", "1024" to "1 MiB", "2048" to "2 MiB", "4096" to "4 MiB"),
                        {save("sotc_rb_stream_max_kb",it)})
                    SotcChoice(if(pt) "Enviar comandos Vulkan por intervalo" else "Periodic Vulkan submission",
                        values["sotc_flush_us"]?:"0",
                        listOf("0" to "OFF", "500" to "0,5 ms", "1000" to "1 ms", "2000" to "2 ms"),
                        {save("sotc_flush_us",it)})
                    Text(if(pt) "Readback antecipado e envio periódico estavam desligados no Adreno. São experimentais: teste um por vez. O aumento das janelas pode usar mais memória e não garante FPS." else "Ahead readbacks and periodic submits were OFF on Adreno. Experimental; test one at a time. Larger windows can increase memory use without improving FPS.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    Text(if(pt) "DMA E MEMÓRIA" else "DMA AND MEMORY",
                        color=SotcPalette.accent,fontWeight=FontWeight.Bold,fontSize=12.sp)
                    SotcToggle(if(pt) "Reusar guardas de heap já validadas" else "Reuse validated heap guards",
                        (values["sotc_heap_fast"]?:"1")=="1",
                        {save("sotc_heap_fast",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Agrupar transferências DMA vizinhas" else "Merge adjacent DMA transfers",
                        (values["sotc_dma_merge"]?:"1")=="1",
                        {save("sotc_dma_merge",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Varrer apenas páginas DMA modificadas" else "Incremental DMA page sweep",
                        (values["sotc_dma_incr"]?:"1")=="1",
                        {save("sotc_dma_incr",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Copiar buffers grandes em paralelo" else "Parallel large-buffer copies",
                        (values["sotc_copy_batch"]?:"1")=="1",
                        {save("sotc_copy_batch",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Liberar arenas assincronamente" else "Asynchronous memory arena eviction",
                        (values["sotc_evict_async"]?:"1")=="1",
                        {save("sotc_evict_async",if(it)"1" else "0")})
                    SotcChoice(if(pt) "Páginas CPU pré-marcadas" else "CPU write-ahead pages",
                        values["sotc_write_ahead_pages"]?:"15",
                        listOf("0" to "OFF", "8" to "8 páginas", "15" to "15 páginas", "31" to "31 páginas"),
                        {save("sotc_write_ahead_pages",it)})
                    SotcChoice(if(pt) "Limite por lote DMA" else "DMA merge limit",
                        values["sotc_dma_merge_max"]?:"16",
                        listOf("8" to "8 MiB", "16" to "16 MiB", "32" to "32 MiB", "64" to "64 MiB"),
                        {save("sotc_dma_merge_max",it)})
                    SotcChoice(if(pt) "Páginas por grupo de arena" else "Vulkan arena grouping",
                        values["sotc_arena_group"]?:"4",
                        listOf("1" to "1 página", "2" to "2 páginas", "4" to "4 páginas", "8" to "8 páginas"),
                        {save("sotc_arena_group",it)})
                    Text(if(pt) "DMA incremental depende de DMA agrupado; cópias paralelas dependem do runtime. Os padrões da 0.1.34 são preservados." else "Incremental DMA depends on DMA merge; parallel copies require runtime support. 0.1.34 defaults preserved.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    Text(if(pt) "CPU, TEXTURAS E PIPELINES" else "CPU, TEXTURE AND PIPELINE CACHES",
                        color=SotcPalette.accent,fontWeight=FontWeight.Bold,fontSize=12.sp)
                    SotcToggle(if(pt) "Reutilizar imagens de profundidade" else "Reuse depth-image twins",
                        (values["sotc_depth_twin"]?:"1")=="1",
                        {save("sotc_depth_twin",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Evitar locks em páginas sem imagens" else "Skip locks on image-free pages",
                        (values["sotc_tc_skip_empty"]?:"1")=="1",
                        {save("sotc_tc_skip_empty",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Cache de samplers Vulkan" else "Vulkan sampler cache",
                        (values["sotc_sampler_memo"]?:"1")=="1",
                        {save("sotc_sampler_memo",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Cache de busca de texturas" else "Texture lookup cache",
                        (values["sotc_find_memo"]?:"1")=="1",
                        {save("sotc_find_memo",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Invalidar caches só no endereço alterado" else "Address-local cache invalidation",
                        (values["sotc_memo_addr_gen"]?:"1")=="1",
                        {save("sotc_memo_addr_gen",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Cache exato de pipelines" else "Exact pipeline-key cache",
                        (values["sotc_pipe_memo"]?:"1")=="1",
                        {save("sotc_pipe_memo",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Busca rápida de render targets" else "Fast render target lookup",
                        (values["sotc_rt_fast"]?:"1")=="1",
                        {save("sotc_rt_fast",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Evitar locks Vulkan redundantes" else "Avoid redundant Vulkan pending-op locks",
                        (values["sotc_pop_fast"]?:"1")=="1",
                        {save("sotc_pop_fast",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Draw direto quando argumentos estão na CPU" else "Direct draw for CPU-resident arguments",
                        (values["sotc_indirect_direct"]?:"1")=="1",
                        {save("sotc_indirect_direct",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Ceder CPU durante esperas" else "Yield CPU during command waits",
                        (values["sotc_cp_yield"]?:"1")=="1",
                        {save("sotc_cp_yield",if(it)"1" else "0")})
                    SotcToggle(if(pt) "Cache de pipelines do driver" else "Persistent driver pipeline cache",
                        (values["sotc_driver_cache"]?:"1")=="1",
                        {save("sotc_driver_cache",if(it)"1" else "0")})
                    SotcChoice(if(pt) "Threads de compilação assíncrona" else "Async shader workers",
                        values["sotc_pipeline_workers"]?:"auto",
                        listOf("auto" to "Auto", "2" to "2", "4" to "4", "6" to "6", "8" to "8"),
                        {save("sotc_pipeline_workers",it)})
                    Text(if(pt) "Já estavam ligados no núcleo da 0.1.34. Os controles servem para comparação individual; desligá-los pode reduzir FPS." else "Already enabled in 0.1.34 native code. These are individual comparison switches; disabling them may reduce FPS.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    Text(if(pt) "EXPERIMENTAL — MUDANÇA VISUAL" else "EXPERIMENTAL VISUAL CHANGE",
                        color=SotcPalette.accent,fontWeight=FontWeight.Bold,fontSize=12.sp)
                    SotcToggle(if(pt) "Sombras distantes intercaladas (visual experimental)" else "Stagger distant shadows (visual experimental)",
                        (values["sotc_shadow_stagger"]?:"0")=="1",
                        {save("sotc_shadow_stagger",if(it)"1" else "0")})
                    Text(if(pt) "Desligada por padrão. Alterna cascatas distantes e pode atrasar sombras em movimento um quadro." else "OFF by default. Alternates far shadow cascades and can lag moving shadows by one frame.",
                        color=SotcPalette.secondary,fontSize=11.sp)
                    SotcToggle(if(pt) "Histórico temporal TAA (ghosts)" else "TAA temporal history (ghosts)",
                        (values["sotc_taa_history"]?:"0")=="1",
                        {save("sotc_taa_history",if(it)"1" else "0")})
                    Text(if(pt) "Desligado por padrão para evitar imagens anteriores arrastadas. A iluminação e a exposição permanecem. Reinicie o jogo após mudar."
                         else "Off by default to avoid trailing previous frames. Lighting and exposure remain. Restart after changing.",
                         color=SotcPalette.secondary,fontSize=11.sp)
                    Text(if(pt) "O modo 60 FPS e as resoluções ficam na tela Inicial. Patches de God of War III não são utilizados."
                        else "60 FPS modes and resolutions are on Home. God of War III patches are not used.",
                        color=SotcPalette.secondary,fontSize=12.sp)
                }
            }
            else -> {
                Text("SHADOW OF THE COLOSSUS",color=SotcPalette.text,
                    fontFamily=FontFamily.Serif,fontWeight=FontWeight.Bold,fontSize=23.sp)
                Text("DAEDALUS • 0.1.35 performance lab",color=SotcPalette.accent,fontSize=13.sp)
                SotcPanel {
                    Text(if(pt) "PORT ANDROID" else "ANDROID PORT",color=SotcPalette.accent,fontWeight=FontWeight.Bold)
                    Text(if(pt) "Port experimental Android de Shadow of the Colossus. Renderer Vulkan específico do SotC, FEX e infraestrutura Android/Bionic."
                         else "Experimental Shadow of the Colossus Android port using the SotC-specific Vulkan renderer, FEX and Android/Bionic infrastructure.",
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
