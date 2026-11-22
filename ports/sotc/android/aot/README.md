# Shadow of the Colossus — ARM64 AOT sem FEX e sem TSO

**Objetivo:** exclusivamente ARM64 AOT nativo, sem TSO e sem fallback FEX. A versão 0.1.53 permanece como referência jogável. O APK 0.1.55 compilou AOT no próprio telefone; a gameplay ainda não foi validada.

## Arquivos reais verificados (21/11/2026)

- CUSA08809 EU 1.01, entrada 0xf120.
- Eboot SHA-256: 21982727c6f97fd415b3af5e99c5e071619c4dcc2248787a701a31a45ab0a4e0.
- libc.prx e libSceFios2.prx foram vinculados sem erro.
- Imagem BBPROBE5: 85.769.980 bytes, 2 módulos, 197 bindings, 687 imports, 714.353 relocations.
- Imagem AOT preparada com 68 patches (396 bytes de payload; 222 bytes efetivamente distintos do original), SHA-256 de6603499b32e3ac0528982a7bb21eccc3a0302591c3a171a52a8ba8f817020a.
- Três funções red-zone: 0xedfb30, 0xf67d2b e 0xf52530. Ainda requerem equivalência funcional no ARM64.

Todos os arquivos do jogo permaneceram no ambiente de trabalho privado. Não enviar executáveis, PRX ou dados do jogo ao GitHub Actions. A imagem preparada ainda contém código x86 para o compilador, NÃO código ARM64 executável.

## Implementações nesta branch

1. **compile_local.py**: valida assinatura, módulos, patches e cobertura; monta clone de boot, usa --target aarch64 --resume-entries --no-callee-saved, **sem --tso**.
2. **port_guest_context.py**: adapta o engine CPU AOT do Bloodborne (pino b6d4cfb6972c84d4029f54765406ec143df3c30e) ao ABI guest_context_get/set do SotC. Salva RIP/RSP após o retorno HLE; preserva FS/GS da thread; evita duplicar o retorno quando troca de fiber.
3. **build_native_cpu.sh**: gera libgow3cpu.so ARM64 e alias libbbcpu.so sem dependências FEX, com verificação de símbolos ABI.
4. **Tests e GitHub Actions**: código sintético e verificação de política sem TSO. Testes NÃO comprovam execução real do jogo.

### Preparar AOT em ambiente privado com os arquivos do jogo

    python3 ports/sotc/android/aot/compile_local.py --game /private/CUSA08809 --prepared /private/sotc-out --out /private/sotc-aot --compiler /private/libbbrecomp.so --bundle-dir /private/bb-recomp-bundle --jobs 3 --shards 64

Com --dry-run apenas valida e prepara a imagem, sem gerar libSotcAot.so.

### Compilar o backend AOT com Android NDK

    SOTC_NDK=/opt/android/ndk/r29 bash ports/sotc/android/aot/build_native_cpu.sh

## Pendências reais

- Compilar libSotcAot.so com tradução completa; checar SSE4a, código indireto, exceções e concorrência.
- Compilar backend em NDK e validar chamadas guest_cpu_*/guest_context_* e fibers na gameplay.
- Integrar AOT no launcher Android e no APK, sem incluir FEX na build AOT.
- Assinar com a chave original do 0.1.53 para instalar por cima, sem apagar dados.
- Medir FPS, física, vídeos e estabilidade com os mesmos trechos (especialmente a floresta).

Não alegar correção completa, gameplay nem ganho de FPS antes dos testes reais. A remoção de TSO não elimina a necessidade de sincronização explícita correta.

## 21/11/2026 — correção real do BBPATCH2

O primeiro compilador abortou com `bad FDE #12150`: o preparador antigo somava incorretamente `0x400000` ao deslocamento de cada patch, destruindo `.eh_frame` no endereço `0x139a4e8`. O `src/probe.c` de 0.1.53 comprova que `memcpy(image+offset)` usa offset DIRETO; `0x400000` é somente base de valores de ponteiro para relocação. A imagem corrigida passou `--scan`: 58.984 FDEs nos três módulos, 1.288 landing pads, 11 funções descobertas. O compilador real foi iniciado em 64 shards sem `--tso`, em ambiente privado; não enviar esses bytes a CI público.

## Resultado real do teste em Android (CUSA08809, 0.1.55)

- Recompilação no celular: **BBR-DONE 0**, **SOTC_AOT_READY**, 67.951 unidades ARM64, 10 com instruções não suportadas, 305,7 s, RSS máximo de 1,32 GiB e libSotcAot.so com 70.017.744 bytes. Modo **sem TSO e sem FEX**.
- A compilação foi validada, mas o lançamento falhou *antes do primeiro frame*, no carregador dinâmico: `CANNOT LINK EXECUTABLE sotc-probe: cannot locate symbol _ZNSt6__ndk113__hash_memoryEPKvm, referenced by libgow3cpu.so`.
- Causa: a biblioteca libgow3cpu.so foi compilada com NDK 30.0.16248370, mas o payload ainda incorporava libc++_shared.so de uma base antiga. Essa versão não exporta a função `std::__ndk1::__hash_memory(void const*, size_t)`.
- Correção: substituir **apenas** libc++_shared.so pela biblioteca que acompanha o NDK utilizado e validar por `verify_libcxx_abi.py` que nenhuma das 2.335 exportações anteriores foi removida e que o símbolo em falta passou a existir. A nova versão possui 2.337 símbolos exportados.
- Lógica para preservar o trabalho de recompilação: `sotcport/user/aot/libSotcAot.so` é parte de `sotcport/user`, que o instalador Android preserva durante atualizações. O jogo deve iniciar sem exigir nova compilação se os patches e a imagem forem os mesmos.
- A correção de link é necessária, mas não comprova gameplay. Testar próxima build no aparelho e investigar quaisquer traps nativos/indiretos restantes sem ativar TSO ou FEX.

## Auditoria de pré-lançamento (21/11/2026) — NÃO LIBERAR AINDA

O usuário compilou o AOT no Redmagic 11 Pro na 0.1.55 (BBR-DONE 0; 305,7 s). O jogo não inicializou devido a `_ZNSt6__ndk113__hash_memoryEPKvm` ausente no `libc++_shared.so` antigo. Foi confirmado que a substituição do NDK 30 exporta esse símbolo e não remove nenhum dos 2.335 símbolos públicos da biblioteca anterior. **Essa correção ainda não prova gameplay.**

Outras falhas identificadas e corrigidas na branch, ainda não incluídas em APK novo:

- O launcher exigirá biblioteca **local** validada: game SHA + patches SHA + cmdline SHA + SHA da imagem vinculada + SHA da biblioteca AOT. Nada de usar silenciosamente biblioteca pré-compilada que não corresponda às configurações.
- BBPATCH2 é aplicado a um clone antes do AOT. O `SOTCCMD1` é pré-incorporado como nova região de dados de **16 KiB alinhada a 16 KiB**; o RIP-relative LEA é alterado *antes* da recompilação. O runtime recebe exatamente essa imagem, sem `--patches` ou `--sotc-cmdline` tardios.
- Os três artefatos `boot-native.bin`, `libSotcAot.so` e `aot-report.json` são validados como conjunto e promovidos com diretório temporário/rollback em caso de falha.
- A rota de empacotamento foi corrigida para **não carregar CPU FEX** por engano. Em modo `SOTC_REQUIRE_ON_DEVICE_AOT=1`, o pacote exige `libgow3cpu.so` AOT, `libbbcpu.so`, compilador e bundle LLVM, `libc++` compatível e manifest `aot_mode: strict`. O jogo AOT não é distribuído.
- O instalador valida os componentes obrigatórios antes de substituir o runtime; os saves e diretório de usuário são preservados na atualização.
- O caminho `--vulkan-only` do código nativo foi corrigido para não depender de `guest_cpu_init` quando não há biblioteca AOT local.
- O compilador agora **recusa o resultado se houver até uma única unidade `bbr_trap`**, e só aceita metadata `compiler_version=1` do bb-recomp oficial sem `--tso`.

**Bloqueio real restante**: o compilador 1.3.0 gera **10 unidades com armadilhas (109 sites)** no SotC:
```
0x688e40 VLoadVectorMasked + VStoreVectorMasked
0xa120b0 VStoreVectorMasked
0xb12bc0 VStoreVectorMasked
0xb132b0 VStoreVectorMasked
0xb139c0 VStoreVectorMasked
0xe104e0 VStoreVectorMasked
0xf0c000 VLoadVectorMasked + VStoreVectorMasked
0x39b5460 VPCMPISTRX (libc.prx)
0x39b5530 VPCMPISTRX (libc.prx)
0x39e31a0 VLoadVectorMasked (libc.prx)
```
A versão oficial disponível no momento **não baixa esses três tipos de operação para AArch64 sem `bbr_trap`**. É necessária uma correção verdadeira do compilador e testes de semântica, não uma tentativa de ignorar essas instruções. O próximo APK só deverá ser gerado após compilar uma biblioteca sem trap, passar a compilação do novo probe/empacotador completo e conferir ELF/dependências/assinatura. Testes sintéticos do GitHub Actions não comprovam gameplay.
