# Shadow of the Colossus — ARM64 AOT sem FEX e sem TSO

**Objetivo:** exclusivamente ARM64 AOT nativo, sem TSO e sem fallback FEX. A versão 0.1.53 permanece como referência jogável. O APK AOT ainda NÃO foi compilado/validado.

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
