# PC #308 depth-only / G-buffer fastpaths — Android ARM64 v0.1.66

## Código transportado

PC de referência com jogo funcional: `AjncSystem/ShadowOfTheColossus-PC`, commit `732cb37d3470d2dad2cc99da19283253c96b53fc` (implementação dos fast paths que chegaram à v0.74). O build Android dessa branch **não** usa mais o commit antigo `27f376d`: o stage copia o GPU real do commit com a PR #308 e aplica os patches Bionic/Adreno/Android na árvore temporária.

Portados juntos, sem atalho parcial:

- `Liverpool::BackAlloc`/ `ExecuteBackOp`: transporte por máscara de dwords que *mudaram de valor*, séries `RelRender`/`RelColor`/`RelDynamic`, e verificação das cópias.
- `Rasterizer::DepthFastBeginCheck`/`DepthFastBeginApply` e `GBufferFastCheck`/`GBufferFastApply`: cache do `RenderState` somente com todos os registros, gerações de imagem, estado de attachment, metadados e barriers consistentes.
- `PrepareRenderState`, `BeginRenderingFast`, `CommitDynamicState` e `Scheduler::BeginRendering`: reutilização sem suprimir draws do jogo.
- Verificações de `ImageSetGeneration`, `MetaEpoch`, `TransitIsNoop`, `gpu_modified_epoch`, `CMASK`, `HTile`, dirty flags, feedback, HUD, LRU, uploads e readbacks. Nada disso deve ser removido de futuros patches.

Android ARM64: `stage_sotc_pc074_arm64.py` substitui somente a comparação SSE de 4 dwords pela máscara exata calculada por dword em ARM, preserva o protocolo de serialização, e troca usos x86 de `rdtsc` por `cntvct_el0` com mesma fonte de tempo para os diagnósticos. Aplica `yield` no spin do CP/draw. A máscara padrão da release PC (bits 39,59,60 desligados; 28/29 ligados) é inicializada somente quando `SOTC_PORT=1`.

### Teste A/B

`SOTC_DEPTH_FAST=0` desativa somente a otimização depth-only; `SOTC_GBUFFER_FAST=0` desativa somente a de G-buffer. Ambos são `1` por padrão. A comparação exige o mesmo trecho salvo, posição e orientação de câmera, aquecimento de shaders e repetição. Relatar `cmds/frame`, FPS, `p95/p99 frametime`, CPU draw, CP e readbacks. O ganho de FPS medido no PC **não** é automaticamente o ganho no Snapdragon.

`SOTC_DEPTHFAST_VERIFY` e `SOTC_DRAW_OPT_VERIFY` são diagnósticos da própria implementação PC, sob demanda. Não deixar ligados em benchmark normal.

## Limites de compatibilidade/funcionalidade do snapshot

O port PC #308 já contém o `TryFillThroughFromCpu` e a otimização de staging power-of-two. Os patches Android antigos `stage_sotc_rt_memo`, `stage_sotc_reg_snapshot`, `stage_sotc_pm4_redundant_regs_064`, `stage_sotc_sun_shadow_cascades_059`, `stage_sotc_stage_spec_cpu` e `stage_sotc_gpu_work_052` não são reaplicados sobre essa árvore porque duplicariam APIs ou alterariam o novo protocolo de dwords da PR #308. Os patches Android específicos de Adreno, TAA, imagem, apresentação AHB, readback e UBO que têm âncoras compatíveis continuam.

**Não confundir recursos removidos com duplicatas**: o `stage_sotc_pc_streaming_051` tinha também uploads assíncronos de geometria da versão PC 0.76, ausentes no commit 732 (0.74), e o patch GPU 052 tinha uploads assíncronos de texturas. Esses dois uploads assíncronos não foram portados nesta etapa; podem afetar travadas em trocas de área e exigem integração independente. `SOTC_BUF_ASYNC_KB` e `SOTC_TEX_ASYNC_KB` antigos não são confirmação de que essas rotinas executam. A validação de FPS e estabilidade ainda depende de teste em aparelho.

## Critérios de entrega

CI 066 faz primeiro testes estáticos, depois compilação Android AArch64 do `libbbgpu.so`, valida os símbolos de apresentação AHB, máscaras do #308 e ausência de FEX no CPU AOT, gera e checa o APK com `versionCode=10066` e `versionName=0.1.66-pc074-depthgb`. O APK publicado pelo Actions é **não assinado**: requer a chave privada fixa original para instalar sobre a versão já existente. Sem execução no celular não declarar melhoria de FPS ou ausência de glitches.
