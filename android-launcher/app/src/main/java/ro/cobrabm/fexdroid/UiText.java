package ro.cobrabm.fexdroid;

import android.content.Context;
import java.util.Map;
import java.util.LinkedHashMap;
import java.util.Locale;

/** English/Portuguese strings for the Android in-game drawer and dialogs. */
final class UiText {
    private static final Map<String,String> PT = new LinkedHashMap<>();
    static {
        PT.put("Screen mode", "Modo de tela");
        PT.put("Centered 16:9", "16:9 centralizado");
        PT.put("Stretch to fill", "Esticar para preencher");
        PT.put("God of War III game folder", "Pasta do jogo God of War III");
        PT.put("Choose folder", "Escolher pasta");
        PT.put("Not a God of War III folder", "A pasta não contém God of War III");
        PT.put("Choose again", "Escolher novamente");
        PT.put("For God of War III 1.09 offline play. They switch at once, while you play.", "Para God of War III 1.09 offline. As alterações valem imediatamente durante o jogo.");
        PT.put("Current-frame Qualcomm filter only. No temporal accumulation. The game stays at the selected resolution; it does not upscale to 720p or 1080p.", "Filtro Qualcomm aplicado apenas ao quadro atual, sem acúmulo temporal. O jogo mantém a resolução selecionada; não amplia para 720p ou 1080p.");
        PT.put("Current-frame Qualcomm filter only. No temporal accumulation. Uses the game resolution selected above; requires restart. Very high resolutions can use significantly more GPU memory.", "Filtro Qualcomm aplicado apenas ao quadro atual, sem acúmulo temporal. Usa a resolução do jogo selecionada acima e exige reinício. Resoluções muito altas podem consumir bem mais memória da GPU.");
        PT.put("Engine active: ", "Geração ativa: ");
        PT.put(" real FPS / ", " FPS reais / ");
        PT.put(" displayed FPS", " FPS exibidos");
        PT.put("Not active yet: enable it and start the game with your own Lossless.dll.", "Ainda inativo: ative e inicie o jogo com seu Lossless.dll.");
        PT.put("Performance HUD — FPS / GPU / CPU", "HUD de desempenho — FPS / GPU / CPU");
        PT.put("Show performance HUD", "Mostrar HUD de desempenho");
        PT.put("Horizontal position", "Posição horizontal");
        PT.put("Vertical position", "Posição vertical");
        PT.put("Left", "Esquerda");
        PT.put("Center", "Centro");
        PT.put("Right", "Direita");
        PT.put("Top", "Topo");
        PT.put("Middle", "Meio");
        PT.put("Bottom", "Base");
        PT.put("Performance HUD", "HUD de desempenho");
        PT.put("Cannot save performance HUD settings.", "Não foi possível salvar as configurações da HUD.");
        PT.put("Bloodframe · Native frame generation", "Bloodframe · Geração de quadros nativa");
        PT.put("Performance model (recommended)", "Modelo de desempenho (recomendado)");
        PT.put("FP16 shaders · Adreno 830 (recommended)", "Shaders FP16 · Adreno 830 (recomendado)");
        PT.put("Motion flow: %.2f (lower = faster)", "Fluxo de movimento: %.2f (menor = mais rápido)");
        PT.put("Apply live", "Aplicar agora");
        PT.put("Frame generation", "Geração de quadros");
        PT.put("Lossless.dll found", "Lossless.dll encontrado");
        PT.put("Lossless.dll missing: import it in Settings → General. The engine cannot start without it.", "Lossless.dll ausente: importe em Configurações → Geral. A geração não pode iniciar sem ele.");
        PT.put("Native Bloodframe · directly adapted from Bloodborne Android. Generated frames are inserted between real game frames, using shaders in your own Lossless.dll.", "Bloodframe nativo · adaptado do Bloodborne Android. Insere quadros gerados entre os quadros reais usando os shaders do seu Lossless.dll.");
        PT.put("The Bloodborne fix uses the original FP16 / FP32 SPIR-V shaders from Lossless.dll. Old DXBC translations may cause ghosting on Adreno 8xx.", "Usa os shaders SPIR-V FP16 / FP32 originais do Lossless.dll. Traduções DXBC antigas podem causar rastros no Adreno 8xx.");
        PT.put("OFF keeps centered 16:9. ON stretches to fill without cropping. System bars stay hidden in both modes.", "Desativado: 16:9 centralizado. Ativado: estica para preencher sem cortar. As barras do sistema ficam ocultas nos dois modos.");
        PT.put("DODGE", "ESQUIVA");
        PT.put("DRAG", "ARRASTE");
        PT.put("DONE", "CONCLUÍDO");
        PT.put("Anisotropic filtering", "Filtragem anisotrópica");
        PT.put("Game default", "Padrão do jogo");
        PT.put("Swipe left or press A to return", "Deslize para a esquerda ou pressione A para voltar");
        PT.put("Game", "Jogo");
        PT.put("Resume game", "Continuar jogo");
        PT.put("Restart game", "Reiniciar jogo");
        PT.put("Unsaved progress is lost", "O progresso não salvo será perdido");
        PT.put("Restart God of War III?", "Reiniciar God of War III?");
        PT.put("Any unsaved progress will be lost.", "Todo progresso não salvo será perdido.");
        PT.put("Cancel", "Cancelar");
        PT.put("Restart", "Reiniciar");
        PT.put("Graphics", "Gráficos");
        PT.put("Graphics settings", "Configurações gráficas");
        PT.put("Controls", "Controles");
        PT.put("Swap Square/Triangle", "Trocar Quadrado/Triângulo");
        PT.put("On-screen controller", "Controle na tela");
        PT.put("Edit controller layout", "Editar layout dos controles");
        PT.put("Drag and resize the buttons", "Arraste e redimensione os botões");
        PT.put("Reset controller layout", "Restaurar layout dos controles");
        PT.put("Quit game", "Sair do jogo");
        PT.put("Quit God of War III?", "Sair de God of War III?");
        PT.put("Quit", "Sair");
        PT.put("God of War III for Android", "God of War III para Android");
        PT.put("Restarting God of War III…", "Reiniciando God of War III…");
        PT.put("Starting God of War III…", "Iniciando God of War III…");
        PT.put("No upscaling", "Sem ampliação");
        PT.put("no FPS limit", "sem limite de FPS");
        PT.put(" FPS limit", " FPS de limite");
        PT.put("Off", "Desativado");
        PT.put("On", "Ativado");
        PT.put("Startup black screen fix", "Correção de tela preta ao iniciar");
        PT.put("Texture corruption fix", "Correção de texturas corrompidas");
        PT.put("OFF keeps the original arena. Texture errors or crashes may occur, especially at higher resolutions. Requires restart.", "Desativado mantém a arena original. Podem ocorrer erros de textura ou falhas, especialmente em resoluções maiores. Requer reiniciar.");
        PT.put("Render resolution", "Resolução de renderização");
        PT.put("Choose the game rendering resolution. Changes apply after restart.", "Escolha a resolução de renderização. As alterações são aplicadas após reiniciar.");
        PT.put("Image", "Imagem");
        PT.put("Sharpening", "Nitidez");
        PT.put("Sharpness: ", "Nitidez: ");
        PT.put("Show FPS", "Mostrar FPS");
        PT.put("Game effects", "Efeitos do jogo");
        PT.put("Disable dynamic shadows", "Desativar sombras dinâmicas");
        PT.put("FPS limit", "Limite de FPS");
        PT.put("Unlimited", "Sem limite");
        PT.put("30 (the game's own)", "30 (original do jogo)");
        PT.put("Above 30 uses the community frame-rate patch (game timing follows the real frame time).", "Acima de 30 utiliza o patch de taxa de quadros da comunidade; o tempo do jogo acompanha o tempo real entre quadros.");
        PT.put("Apply & restart", "Aplicar e reiniciar");
        PT.put("Apply", "Aplicar");
        PT.put("The settings could not be saved.", "Não foi possível salvar as configurações.");
        PT.put("Frames", "Quadros");
        PT.put("2× frames", "2× quadros");
        PT.put("3× frames", "3× quadros");
        PT.put("4× frames", "4× quadros");
        PT.put("Flow scale", "Escala do fluxo");
        PT.put("Performance mode", "Modo de desempenho");
        PT.put("1.0 (best quality)", "1.0 (melhor qualidade)");
        PT.put("0.25 (fastest)", "0.25 (mais rápido)");
        PT.put("Game settings", "Configurações do jogo");
        PT.put("Cheats", "Trapaças");
        PT.put("Cheats applied", "Trapaças aplicadas");
        PT.put("The cheats could not be saved", "Não foi possível salvar as trapaças");
        PT.put("Skip the online/offline screen", "Pular tela online/offline");
        PT.put("Start straight at the main menu, offline (there is no PSN here)", "Iniciar diretamente no menu principal offline");
        PT.put("Skip startup intros", "Pular introduções");
        PT.put("The logos and intro movie at start", "Logotipos e vídeo de introdução");
        PT.put("Free camera", "Câmera livre");
        PT.put("Toggle it with Cross + L3", "Alternar com X + L3");
        PT.put("Debug menu", "Menu de depuração");
        PT.put("The game's own debug menu; needs its font files", "Menu de depuração do jogo; requer os arquivos de fonte");
        PT.put("Infinite health", "Vida infinita");
        PT.put("Your HP refills to full every frame", "A vida é restaurada a cada quadro");
        PT.put("These are patches to the game: Apply restarts it (unsaved progress is lost).", "Aplicar os patches reinicia o jogo; o progresso não salvo será perdido.");
        PT.put("Open game menu", "Abrir menu do jogo");
    }
    static boolean portuguese(Context context) {
        return "pt".equals(context.getSharedPreferences("gow3", Context.MODE_PRIVATE).getString("language", "en"));
    }
    static String gameLanguage(Context context) {
        if (!portuguese(context)) return "1";
        android.content.SharedPreferences prefs=context.getSharedPreferences("gow3",Context.MODE_PRIVATE);
        return com.gow3.android.data.GameSfo.portugueseLanguage(
            prefs.getString("game_dir",null),prefs.getString("update_dir",null));
    }
    static String get(Context context, String text) {
        if (text == null || !portuguese(context)) return text;
        String translated = PT.get(text);
        if (translated != null) return translated;
        for (Map.Entry<String,String> entry : PT.entrySet()) {
            if (text.equals(entry.getKey().toUpperCase(Locale.ROOT)))
                return entry.getValue().toUpperCase(new Locale("pt", "BR"));
        }
        // Dynamic subtitles retain their numbers and version identifiers.
        for (String key : new String[]{"God of War III for Android", "No upscaling", "no FPS limit", " FPS limit", "Sharpness: "})
            text = text.replace(key, PT.get(key));
        return text;
    }
    private UiText() {}
}
