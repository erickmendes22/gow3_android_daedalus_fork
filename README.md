# God of War III — Daedalus Fork · Bionic

**Versão: 2.1.6-daedalus.4-bionic**

**Português (Brasil)** | [English](README.en.md)

Fork mantido por **erickmendes22 — [Daedalus Emulator](https://www.youtube.com/@daedalusemulator)**, baseado no [projeto Android de zFitness](https://github.com/zFitness/gow3_android) e no trabalho dos colaboradores dos projetos de origem.

## Runtime nativo Android/Bionic

Esta versão utiliza **Bionic, a biblioteca de sistema nativa do Android**, com apresentação gráfica por **AHardwareBuffer** e integração Vulkan para drivers do sistema ou personalizados.

O código original do jogo continua sendo traduzido de **x86-64 para ARM64 pelo FEXCore**, enquanto o renderizador baseado no shadPS4 traduz os gráficos para Vulkan.

O projeto é dedicado a **God of War III Remastered**.

## Principais recursos

- **Seleção de drivers:** driver do sistema, Turnip integrado ou driver personalizado.
- **Resoluções de renderização selecionáveis**, incluindo 720p, 900p e 1080p.
- **Melhorias de desempenho e sincronização gráfica**, com otimizações de shaders, cache e transferências de dados.
- **Correções de coerência do cache de texturas** no renderizador.
- **Patches opcionais** para efeitos gráficos, sombras, vídeos e correção de texturas corrompidas.
- **Instalação direta de PKG**, incluindo atualizações para o jogo selecionado.
- **Contador de FPS configurável:** visibilidade, posição e tamanho.
- **Interface em inglês e português brasileiro**, incluindo as configurações durante o jogo.
- **Seleção de português no jogo** conforme a edição e os idiomas disponíveis nos arquivos instalados.
- **Gerenciamento de saves e exportação de logs.**

A versão atual utiliza **renderização direta, sem FSR e sem LSFG**.

## Requisitos

- **Android 11 ou superior.**
- Dispositivo **ARM64 — arm64-v8a**, sem necessidade de root.
- GPU e driver compatíveis com os recursos Vulkan exigidos pelo runtime.
- Sua própria cópia de **God of War III Remastered**.

Os patches dependem da edição e da versão do executável. Os patches disponíveis no catálogo são voltados à atualização **01.02**.

## Instalação

1. Baixe e instale o APK em [Releases](https://github.com/erickmendes22/gow3_android_daedalus_fork/releases).
2. Conceda a permissão de acesso aos arquivos solicitada na primeira abertura.
3. Selecione uma pasta com o jogo já extraído ou utilize **Instalar PKG**.
4. Configure a resolução, os patches e o driver desejados.
5. Inicie o jogo.

O desempenho varia conforme o aparelho, o driver, a resolução e os efeitos selecionados.

## Créditos

- **erickmendes22 / Daedalus Emulator** — manutenção desta fork e adaptações para Android.
- **[zFitness/gow3_android](https://github.com/zFitness/gow3_android)** — projeto Android usado como base.
- **[ducvd89/Bloodborne-Android](https://github.com/ducvd89/Bloodborne-Android)** — infraestrutura Android/Bionic adaptada para o carregamento de drivers Vulkan, apresentação por AHardwareBuffer, preparação nativa e compilação de dependências.
- **[FelipePrado0/gow3_pc](https://github.com/FelipePrado0/gow3_pc)** e **[R-V-L/gow3_pc](https://github.com/R-V-L/gow3_pc)** — projetos de origem e melhorias do port.
- **[deadinside28/bloodborne_pc](https://github.com/deadinside28/bloodborne_pc)** — projeto que fundamentou a cadeia de ports.
- **[cuesta4/shadPS4](https://github.com/cuesta4/shadPS4)** e **[equipe do shadPS4](https://github.com/shadps4-emu/shadPS4)** — renderizador e correções gráficas.
- **[FEX-Emu](https://github.com/FEX-Emu/FEX)** — tradução dinâmica do código x86-64 para ARM64.
- **[fexdroid](https://github.com/cobrabm12/fexdroid)** — infraestrutura Android utilizada pelo projeto de origem.
- **kvicken, cuesta4 e illusion0001** — patches e trabalhos que deram origem às adaptações de resolução, texturas, vídeos e taxa de quadros.
- **StevenMXZ, WinNative-Emu e colaboradores do Mesa/Turnip** — drivers integrados e respectivas correções.

Mais atribuições estão nos [avisos do runtime Bionic](tools/android/bionic/NOTICE.txt) e nas licenças dos componentes utilizados.

## Suporte

**YouTube:** [@daedalusemulator](https://www.youtube.com/@daedalusemulator)  
**Problemas e sugestões:** [GitHub Issues](https://github.com/erickmendes22/gow3_android_daedalus_fork/issues)

Ao relatar um problema, informe o aparelho, o driver, a versão do jogo e anexe os logs exportados pelo aplicativo.

## Licença

**GNU GPL v2 ou posterior.** Consulte [LICENSE](LICENSE). Os componentes de terceiros mantêm suas respectivas licenças.

Nenhum arquivo do jogo é distribuído. Este projeto não é afiliado à Sony Interactive Entertainment ou ao Santa Monica Studio.
