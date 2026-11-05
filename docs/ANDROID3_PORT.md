# Port seletivo da base Android 3

Referência: zFitness/gow3_android, tag `v2.1.6-android3`, commit
`92db45cf9e0fbc4e9e4fea9d682f76d0d56f9eba`.
Base do fork preservada: `7ebfbc4aebe687f35674b716865f1925030df732`.

## Alterações portadas

- Entrada: ler `l2=`/`r2=` como pressão analógica e ativar também o bit digital
  acima do mesmo limiar usado no controle físico. Manter o modo silencioso de log
  do fork. O botão de touchpad na tela passa a representar o lado direito (pausa).
- Android: evitar a varredura SDL de controles quando PadBridge já fornece a entrada.
- Diálogos: ligar a ponte de texto Android no runtime e permitir confirmar/cancelar
  com controle. Na adaptação, o AlertDialog também recebe o listener de teclas;
  ambos os eventos são consumidos e o diálogo é fechado após responder. Se a
  ponte de arquivo não puder ser criada, o runtime consulta o fallback correto.
- Save: prazo de cancelamento do diálogo e fechamento efetivo do overlay; importar
  saves usando INSTALL_DIR_SAVEDATA/TITLE_ID do SFO, em vez de um CUSA fixo.
- Vulkan: escolher uma fila com capacidade sparse binding; evitar ponteiro nulo
  na captura e ler os dados da cópia host do constant ring.
- Scheduler: instalar o próximo RecordChunk antes de entregar o anterior, com
  proteção da transferência em KickRecording.
- Texturas: filtragem anisotrópica opcional 2x/4x/8x/16x, padrão do jogo mantido,
  com opção na Home e no diálogo Android em inglês/português.
- Configuração: o menu nativo preserva chaves que pertencem ao launcher ao salvar.
- Patches: validação completa antes de aceitar as escritas de cada patch;
  assinaturas obrigatórias quando há imagem real; limites de alvo/operando/escrita.

## Mantido, sem duplicar ou substituir

- A coerência de texturas a101edb já estava portada; a implementação do fork ainda
  protege os caminhos rápidos enquanto existem escritas pendentes.
- O limite de oito submissões e a eliminação da espera de cópias vazias permanecem.
- A navegação direta do arquivo de controle na lista de saves permanece: funciona
  mesmo se o jogo parar de chamar scePadReadState, ao contrário de depender apenas
  de um snapshot publicado por essa chamada.
- A preservação e o preenchimento de chaves ausentes do INI permanecem, assim como
  a preservação de saves/backups em atualizações. Não foi introduzida uma segunda
  migração de diretórios para gow3data com funcionalidade equivalente.
- As resoluções diretas verificadas no CUSA01715 e a apresentação única de 1080p
  permanecem. Os presets 900p/1080p experimentais e a troca completa dos catálogos
  por região da base não foram importados: não substituem nossa validação do
  executável e podem alterar a seleção efetiva de patches/FPS. A compatibilidade
  de títulos suportados pelo fork não foi ampliada nesta revisão.
- Não foi portada a opção de intensidade de rumble SDL: no Android a entrada usa
  PadBridge, e essa opção não implementa uma ponte de vibração para o aparelho.
- Os controles removidos de FSR, as traduções e a identidade Daedalus Fork permanecem.
- Readbacks Mode/Readback Linear, fontes e flags de build do Turnip não foram alterados.

## Verificação

Testes Android existentes; testes nativos de settings/pad edges/diálogos; testes
JVM de SFO, importação de saves e INI; regressões de validação de patches, captura,
fila sparse, RecordChunk e coerência de texturas. Compilação ARM64 e APK pelo Actions.
A validação em hardware continua sendo feita pelo usuário; não se afirma ganho
medido de FPS apenas pelos testes de código.
