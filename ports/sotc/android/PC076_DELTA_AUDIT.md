# Shadow of the Colossus: divergências do PC funcional para Android ARM64

Verificação de código: 2026-11-22. **A referência é [AjncSystem/ShadowOfTheColossus-PC](https://github.com/AjncSystem/ShadowOfTheColossus-PC), release v0.76.2 (2026-11-17)**, não o projeto experimental `SotC-project/sotc-pc` sem releases. A stage Android ainda lê o renderer do commit fixo `27f376d602cefad357299295fa51edad587272d5` do primeiro projeto. A cópia não é um merge de todas as melhorias posteriores.

## Deltas já transportados

- PC `eba9ee46c35672b6226275abe57ebde7803dfce6`: reutilização por classes de potência de dois de staging grande: `stage_sotc_pc_streaming_051.py`, cache com validação de tick e limite móvel.
- PC `26e742030b08cb13471ebce0fc20c2a61d779d8b`: uploads de geometria >=256 KiB em threads de cópia, `JoinAsyncUploads` antes de submit, no readback e no destrutor; **já implementado em Android** pelo mesmo stage 051, não reaplicar.
- PC `7acae33d5a71785680994e3b46190dca4006f83b`: reserva de staging maior comprovada no PC. No PC de 12 GiB+ subiu para 768 MiB e reduziu alocações/travamentos no carregamento de área. Android 0.1.65 agora usa **128 MiB por tipo de memória abaixo de 10 GiB físicos e 256 MiB a partir desse limite**, sem a reserva de 768 MiB; o usuário pode usar `SOTC_STAGING_LARGE_KEEP_MB=0/128/256` para A/B. A variável `auto` usa detecção nativa via `sysconf`.
- Vulkan pipeline/vertex command-state memo e slot de descritores: `stage_perf_fastpaths.py`, com invalidação no fim do render pass. **Não equivale** à otimização completa de render targets do PC.
- Tentativas Android `SOTC_PM4_REDUNDANT_REGS` ficam desligadas por padrão: na 0.1.64 não houve ganho mensurável de FPS com 32,9% de duplicatas. Tentativas de draws indiretos vazios e clears de sombras adicionais foram revertidas.

## Deltas reais ainda NÃO equivalentes ao PC 0.76.2

1. **Depth-only/G-buffer fast paths (PC v0.74, Lukto02 PR #308, commit `732cb37d3470d2dad2cc99da19283253c96b53fc`)**: dependem de `Liverpool::DrawRelSerial`, transporte exato de dwords alterados, `DepthFastMemo`, `GBufferFastCheck/Apply`, `TextureCache::ImageSetGeneration`, `MetaEpoch`, `gpu_modified_epoch`, `TransitIsNoop`, `Scheduler::BeginRendering` com token e `CommitDynamicState` memoizado. O `stage_sotc_rt_memo.py` Android é outro mecanismo, não inclui toda essa cadeia e **não autoriza afirmar que a PR #308 já foi portada**. A PR #308 teve no PC 0 divergências em dezenas de milhões de verificações e ganhos de processamento dos draws, mas isso não estabelece FPS Android. Não ativar atalhos de G-buffer antes de comparar estados e efeitos colaterais de cada draw. Fontes: `docs/sotc/DEPTH-FASTPATH.md`, `docs/sotc/GBUFFER-FASTPATH.md`, `gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.{h,cpp}` e `gpu/shadps4/video_core/amdgpu/liverpool.{h,cpp}` no PC v0.76.2.
2. **PC v0.74.2 pipeline de shader/bind e depth**: uma variante precisava casar os bindings do LOD feedback com o layout e outra enviava bytes para um buffer depth com formato diferente. Comparar `vk_pipeline_cache`, `vk_rasterizer` e `buffer_cache` staged com a árvore real antes de portar. Manter fallback de pipeline e coerência de formatos; nunca pular draw apenas porque a criação falhou.
3. **PC v0.76.1 AMD quad-swizzle**: correção específica para arestas de triângulos e linhas no céu em placas AMD; não ativar em Adreno sem reprodução do problema e validação SPIR-V.
4. **PC v0.76.2 SSE4a/BI1/LZCNT para Intel**: código x86 que aplica trampolins no Windows; **não transportar** para CPU AOT ARM64 nativa (nem reintroduzir FEX/TSO).
5. **PC v0.75 mixer NGS2**: separável de render e FPS; não é a causa indicada pelos logs da floresta. Eventual port só com ABI do som Android e testes dedicados.

## Transporte seguro do próximo bloco (depth/G-buffer)

- Atualizar a cópia staged do GPU preservando patch Android em `stage_renderer.py` e AHB em `wire_ahb.py`, em vez de trocar o commit de PC às cegas.
- Portar o rastreamento de dwords relevantes por valor do CP para a draw thread **antes** de aplicar `BeginRenderingFast`; na 0.1.64 a comparação de blocos PM4 desnecessários isolada não ganhou FPS.
- Copiar e adaptar as verificações exatas de `DepthFastBeginCheck` e `GBufferFastCheck`, incluindo geração de imagem, estados de attachment, layout, `CMASK/HTILE`, clear, feedback e invalidações a cada comando/ação de shader. Preservar efeitos LRU, writes e readbacks.
- Implementar `VERIFY` de equivalência por draw e bit de opt-out, antes de ligar por padrão. Validar A/B no mesmo trecho com contagem de draw, tempo da thread de comandos, p95/p99 de frametime e comparação visual. A evidência de PC (+4,4% FPS no templo/santuário) não é previsão quantitativa para Redmagic.

## Entrega 0.1.65 e limitações

- Aplicação `com.sotc.android.daedalus`, `versionCode=10065`, AOT estrito ARM64 sem FEX/TSO, mantendo a ponte AHardwareBuffer e testes da assinatura/manifesto.
- Build do renderer: `.github/workflows/sotc-aot-057-flatbuf-native.yml` (nome da execução 0.1.65); APK: `.github/workflows/sotc-aot-065-apk.yml`, depende explicitamente do artefato nativo 0.1.65 e rejeita o atalho indireto revertido.
- O artefato de CI é **não assinado**: atualizar uma instalação existente exige assinar fora do CI com a mesma chave privada original. Não inventar uma chave nova nem chamar o APK unsigned de atualização instalável. Nenhum teste de FPS ou instalação em aparelho foi realizado pelo CI.
