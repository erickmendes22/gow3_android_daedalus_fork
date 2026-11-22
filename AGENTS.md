# AGENTS.md — Shadow of the Colossus Android

## Obrigação de entrega

Quando a tarefa for corrigir/otimizar o port `ports/sotc/android` e gerar um APK, **não encerre depois de uma análise, de uma alteração isolada, de um diagnóstico ou de uma compilação parcial**. Continue na mesma execução: localizar a causa no código e nos logs, implementar alterações justificadas, testar, corrigir eventuais falhas de compilação, gerar o **APK atualizado** e informar o artefato e o commit exato. Após falha de build, analise a primeira causa real, conserte-a e reexecute o estágio mínimo necessário; não recomponha tudo desnecessariamente. O requisito de entrega não autoriza declarar sucesso sem artefato nem inventar testes.

**Bloqueios reais:** caso a sessão não tenha acesso à assinatura privada original, às dependências, aos artefatos, ao executor de compilação ou às permissões necessárias, registre precisamente o impedimento; produza e valide, se possível, um APK **não assinado** e identifique-o como tal, jamais como APK instalável sobre o anterior. Não altere nem substitua silenciosamente a chave de assinatura.

## Referência do PC — verifique a implementação, não apenas o README

- Referência funcional, com releases: `AjncSystem/ShadowOfTheColossus-PC`, preferindo a release estável atual e registrando tag/commit. Não substitua pelo `SotC-project/sotc-pc` experimental sem releases.
- Aplique **deltas reais de código** e confirme que não foram previamente integrados pelo Android, inclusive por `ports/sotc/android/stage_*.py`. Examine a cadeia `stage_renderer.py` -> `wire_ahb.py` -> compilação nativa -> empacotamento -> assinatura.
- Priorize as partes demonstravelmente custosas nos logs: CPU/PM4, fila e gravação Vulkan por draw, preparação de G-buffer e depth, bindings, readbacks, texturas e stalls de áreas. Não confunda redução de draw/CPU com remoção de geometria ou sombras.
- Não transplante código dependente de Windows, AVX/Intel, DirectX/DLSS, GPU Radeon ou funções de plataforma sem adaptação ao Android ARM64/Adreno/Turnip e testes de equivalência.
- Caminhos rápidos de profundidade e G-buffer devem preservar HTile, CMASK, clears, LRU, epochs da cache, transições, barreiras, layout/formatos, estado dinâmico, uploads/readbacks e efeitos de renderização. Mudanças sem validação adequada ficam opcionais/desligadas e podem ser revertidas.
- Experimentos revertidos (draws indiretos vazios, limpezas Vulkan adicionais de sombras, PM4 exato sem ganho mensurável) **não devem voltar sem evidência nova e específica**. Não repita patches de sombras do sol ou cascatas que não foram aplicados/que não removeram as sombras no teste.
- Preserve o **AOT ARM64 sem FEX e sem TSO**, o pacote `com.sotc.android.daedalus`, saves, controles, AHB, a assinatura fixa e o fluxo de atualização do APK.

## Critério mínimo para cada entrega

1. Registrar baseline, origem upstream, hipótese fundamentada em função e trecho exatos e previsão de efeito.
2. Implementar no fonte **usado efetivamente pelo build**; incluir testes source-drift, compilação e verificações de invariantes. Desligar mudanças experimentais sem equivalência demonstrada.
3. Rodar preflight e compilar/validar a biblioteca `libbbgpu.so` ARM64 com AHardwareBuffer, e o runtime CPU AOT sem FEX/TSO. Não anunciar sucesso por build apenas da biblioteca.
4. **Bloqueio de boot obrigatório:** antes do APK, execute `ports/sotc/android/verify_sotc_link.py` sobre `libbbgpu.so` e o executável ARM64 `gow3-probe`, e repita com os dois ELFs exatos extraídos do payload final (`sotc-probe` e `libbbgpu.so`). Compare **todas** as importações fortes `runtime_*` com as exportações dinâmicas do host, além de símbolos C++ internos; `ld` aceitar biblioteca compartilhada com indefinidos não significa que `dlopen(RTLD_NOW)` funcionará no Android. Nenhum APK pode sair se essa validação não passar. A v0.1.66 perdeu símbolos `Vulkan::Dlssg` e a 0.1.67 perdeu `runtime_memory_clamp_gap_hits`; nunca repetir esse ciclo.
5. Construir APK com versão nova, conferir `aapt`, hashes do payload, conteúdo `arm64-v8a`, `zipalign` e `apksigner` se houver chave fixa. Testar instalação sobre a versão anterior quando houver aparelho/ADB disponível.
6. Publicar o link **real** da execução/artefato GitHub Actions e SHA do commit. Diferenciar: testes estáticos, compilação nativa, APK criado, APK assinado, teste em aparelho, ganho de FPS medido.
7. Se um estágio falhar, corrigir e repetir até o APK **ou bloqueio externo comprovado**, sem cair num ciclo de builds sem alteração fundamentada.
