package ro.cobrabm.fexdroid;

import android.content.Context;
import java.util.Map;
import java.util.LinkedHashMap;
import java.util.Locale;

/** English/Portuguese strings for the Android in-game drawer and dialogs. */
final class UiText {
    private static final Map<String,String> PT = new LinkedHashMap<>();
    static {
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
        PT.put("Return to launcher", "Voltar ao launcher");
        PT.put("Exit application", "Sair do aplicativo");
        PT.put("Back to launcher?", "Voltar ao launcher?");
        PT.put("Exit Shadow of the Colossus app?", "Sair do aplicativo Shadow of the Colossus?");
        PT.put("Button size", "Tamanho dos botões");
        PT.put("Camera sensitivity", "Sensibilidade da câmera");
        PT.put("Shadow of the Colossus patches", "Patches de Shadow of the Colossus");
        PT.put("Edit patches in launcher", "Alterar patches no launcher");
        PT.put("On-screen controller size", "Tamanho do controle na tela");
        PT.put("Right-stick camera sensitivity", "Sensibilidade da câmera do analógico direito");
        PT.put("Compact (90%)", "Compacto (90%)");
        PT.put("Normal (110%)", "Normal (110%)");
        PT.put("Large (125%)", "Grande (125%)");
        PT.put("Extra large (140%)", "Muito grande (140%)");
        PT.put("Slow (0.85×)", "Lenta (0,85×)");
        PT.put("Normal (1.15×)", "Normal (1,15×)");
        PT.put("Fast (1.45×)", "Rápida (1,45×)");
        PT.put("Adjust all touch buttons immediately", "Ajusta o tamanho de todos os botões imediatamente");
        PT.put("Right analogue stick", "Analógico direito");
        PT.put("Drag to move buttons; tap DONE to save", "Arraste para mover os botões; toque em Concluir para salvar");
        PT.put("Shadow of the Colossus", "Shadow of the Colossus");
        PT.put("Starting Shadow of the Colossus…", "Iniciando Shadow of the Colossus…");
        PT.put("Restart Shadow of the Colossus?", "Reiniciar Shadow of the Colossus?");
        PT.put("On-screen controller size", "Tamanho dos botões na tela");
        PT.put("Change game patches in the launcher's Patches tab.", "Altere os patches na aba Patches do launcher.");
        PT.put("Back to launcher?", "Voltar ao launcher?");
        PT.put("Recompile AOT", "Recompilar AOT");
        PT.put("CPU", "CPU");
        PT.put("GPU", "GPU");

    }
    static boolean portuguese(Context context) {
        String selected=context.getSharedPreferences(SotcPaths.prefsName(context), Context.MODE_PRIVATE)
            .getString("language","system");
        if ("system".equals(selected)) return java.util.Locale.getDefault().getLanguage().equals("pt");
        return "pt".equals(selected);
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
