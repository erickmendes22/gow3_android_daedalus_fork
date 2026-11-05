# Experimento Bionic — Daedalus Fork

Branch: `experimental-bionic`, criada de `gow3` no commit
`b0f2d8c7be59c3f3e1dc24883c460b63c0eb1c7d`.

## Estado da integração

O launcher experimental inicia diretamente o runtime Android/Bionic, sem Debian, Xvfb ou
carregador glibc. O pacote usa o identificador `com.gow3.android.bionic`, nome com sufixo
“Bionic” e versão `2.1.6-android3-bionic-experimental`; instala ao lado da versão estável.
Requer Android 11/API 30 ou superior e ARM64. A branch `gow3` permanece preservada.

- CPU/FEX preservado na revisão `fb925d6fc5cc8576bf0f9ae6978fc6d912485593`.
- GPU com carregador Android ICD/HAL; apresentação por AHardwareBuffer, ownership FOREIGN
  e sync-fd, ligada ao SurfaceView pelo receptor JNI `Gow3Present`.
- Entrada PadBridge, controles virtuais, áudio PCM por FIFO e IME conectados ao launcher.
- Preparação nativa de `boot-linked.bin`, `content.bin` e `eboot.elf`; o ELF decodificado
  fica disponível para as verificações de assinatura/bytes dos patches existentes.
- CPython 3.13.7 compilado com NDK/Bionic executa os mesmos scripts de patches, resolução,
  FPS, sombras, idioma, configuração e composição de updates da versão atual.
- `orbis-pkg-util` compilado para `aarch64-linux-android`, com o mesmo CLI e revisão da
  instalação PKG estável. Sem mudar as regras de seleção de pasta/update do launcher.
- Alocações de TLS, handles de thread e atributos entregues ao guest usam memória baixa
  no Android, pois o jogo armazena alguns ponteiros em 40 bits.
- Gen8 `0x44xxxxxx`: V37 patched fixado por hash como padrão automático. Outras GPUs:
  driver Android do sistema. Uma falha do driver solicitado encerra a inicialização;
  não há fallback silencioso.
- Lossless Scaling/lsfg-vk glibc não é carregado no runtime Bionic; a opção do menu do jogo
  fica indisponível neste experimento. Não foi portado nesta etapa.

A integração não comprova execução do jogo no aparelho. Precisam ser validados no Redmagic:
carregamento do driver/HAL, apresentação e cores, áudio, controles/IME, PKG/updates, saves,
patches e desempenho. Não há medição de FPS Bionic nem correção comprovada para o relato de
tom branco do android3. Shader de cor, readbacks e coerência de texturas foram preservados.

## Seleção de driver no launcher

Na tela inicial do APK Bionic, **Vulkan Driver / Driver Vulkan** permite selecionar:

- Automático: mantém o V37 patched no Adreno Gen8 e o sistema nas demais GPUs.
- Driver do sistema: usa o carregador Vulkan do Android, sem o Turnip incluído/importado.
- Turnip Gen8 V37 patched incluído.
- Drivers importados pelo botão **Import driver ZIP / Importar ZIP do driver**.

O importador aceita o formato AdrenoTools com `meta.json` (`schemaVersion=1`, `name`,
`libraryName`, `minApi`) e biblioteca Android ARM64. A seleção é aplicada na próxima
inicialização do jogo. Uma falha do driver escolhido é reportada, sem trocar de driver.

Os pacotes são validados e instalados em `files/gpu-drivers/<sha256-do-zip>`, fora da
pasta `gow3port` substituída em atualizações do runtime. A extração usa área temporária,
limites de tamanho e promoção após validar metadados/ELF; um ZIP inválido preserva os
pacotes anteriores. Pacotes com ABI incorreta, dependências glibc ou Android mínimo
superior ao aparelho são rejeitados. O seletor aparece somente no APK Bionic.

Esse recurso usa o carregador ICD/HAL já validado na branch, compatível com pacotes
AdrenoTools. Não adiciona uma segunda implementação de `libadrenotools`.

## Driver enviado

| Campo | Valor |
| --- | --- |
| Nome | Turnip Gen8 V37 patched |
| Autor | StevenMXZ |
| Arquitetura / libc | AArch64 / Android Bionic (`libc.so`) |
| Biblioteca | `libvulkan_freedreno.so` |
| Entrada exportada | `HMI` (Android Vulkan HAL) |
| minApi declarado | 28 |
| SHA256 do ZIP | `c03b5791610edfc9a9b1f42faeef6b37b07b332a0d5e3a29baf6ddc0a82e0dac` |
| SHA256 da biblioteca | `31b4f16fed6bc0c60d80715067845d1ae34761fcbc1fc37e41e80d1de29a8b4e` |

O ZIP anexado é idêntico ao arquivo publicado em:
https://github.com/StevenMXZ/Adreno-Tools-Drivers/releases/tag/v37

Não confundir com `Turnip_Gen8_V37.zip` (sem `patch`), incluído no Bloodborne.
A variante enviada incorpora patches/hacks do WinNative segundo as notas do autor.
O `driverVersion` em seu meta.json é `Vulkan 1.4.359`; não é uma versão consultada no hardware.

Dependências declaradas: `libhardware.so`, `liblog.so`, `libnativewindow.so`, `libsync.so`,
`libm.so`, `libz.so`, `libdl.so`, `libc.so`. `hw_get_module` é um símbolo requerido, portanto
esta dependência precisa ser resolvida pelo processo Bionic no telefone. A inspeção estática
não comprova o carregamento nem o desempenho no Redmagic 10 Pro.

O driver declara API 28, mas o verificador desta etapa compila para API 30. Isso não significa
que o futuro runtime ou apresentador completo possam funcionar em API 28. O apresentador
Bloodborne usa ASurfaceControl (API 29) e setOnCommit (API 31) para seu melhor caminho FIFO;
sua alternativa em API 29/30 pode apresentar a metade da frequência. Essa decisão ainda
precisa ser validada na migração do GoW III.

## Compilar e verificar

```sh
GOW3_NDK=/caminho/android-ndk-r29 bash tools/android/bionic/build_driver_check.sh
```

Opcionalmente, use o ZIP local (mesmos hashes obrigatórios):

```sh
GOW3_NDK=/caminho/android-ndk-r29 \
GOW3_BIONIC_DRIVER_ZIP=/caminho/Turnip_Gen8_V37_patch.zip \
bash tools/android/bionic/build_driver_check.sh
```

Saída: `out/bionic-driver-check/{bin,drivers,check-driver.sh}`. Esta não é uma distribuição
do runtime completo. A STL estática é usada somente neste executável de diagnóstico isolado;
o runtime com várias bibliotecas deve compartilhar uma única `libc++_shared.so`.

Dentro de um diretório executável privado do app, com seus binários e drivers adjacentes:

```sh
/system/bin/sh check-driver.sh
GOW3_BIONIC_DRIVER=system /system/bin/sh check-driver.sh
GOW3_BIONIC_DRIVER=gen8 /system/bin/sh check-driver.sh
```

O código de saída 0 confirma apenas os pré-requisitos consultados, não apresentação de
quadros, jogo funcional ou vantagem de desempenho. Falhas de `dlopen` registram a dependência
ou erro do linker. Não instale o verificador como substituto de `gow3-probe`.

## Compilar os componentes do jogo

Pré-requisitos do host: CMake, Ninja, pkg-config, compilador, Python, NDK r29 e um prefixo de
headers contendo Boost, robin-map, VMA e o executável host glslangValidator. Em CI pode ser
usado o mesmo prefixo de dependências da build glibc. Os submódulos devem estar inicializados.

```sh
GOW3_NDK=/caminho/android-ndk-r29 \
GOW3_BIONIC_HEADERS=/caminho/prefixo/usr \
GOW3_BIONIC_DRIVER_ZIP=/caminho/Turnip_Gen8_V37_patch.zip \
bash tools/android/bionic/build_runtime.sh
```

Saída: `out/bionic/bin`, `out/bionic/lib` e `out/bionic/drivers/gen8`. O runtime usa uma única
`libc++_shared.so`; as ferramentas independentes de preparação e diagnóstico têm STL estática.
`--link-only` reaproveita CPU/GPU já compiladas para refazer o executável e verificações.
O script não produz APK nem substitui o runtime instalado.

## APK experimental

Requisitos adicionais: JDK 25, Android SDK 37.0/build-tools 35.0.0, Rust 1.90.0 com target
`aarch64-linux-android`, make e compilador host para o Python de preparação.

```sh
GOW3_NDK=/caminho/android-ndk-r29 \
GOW3_BIONIC_HEADERS=/caminho/prefixo/usr \
ANDROID_HOME=/caminho/android-sdk \
bash tools/android/bionic/build_apk.sh
```

`--package-only` reaproveita os componentes nativos já compilados. O APK é assinado com
chave local de desenvolvimento, destinado somente a testes. Uma chave diferente entre
máquinas impede atualizar uma instalação experimental anterior sem reinstalação.

O workflow `Bionic APK (experimental)` compila somente `experimental-bionic`, verifica o
launcher antes da compilação nativa e publica APK/SHA256 como artifacts. Não publica release.
A validação exige identidade separada, hash do runtime e driver original; rejeita conteúdo
executável do jogo/PKG e layouts glibc. O APK contém apenas runtime e ferramentas.

## Verificação e limites

- A configuração da GPU é auditada antes da compilação da CPU/GPU. Headers do host podem
  ser usados, mas bibliotecas importadas e caminhos de busca devem pertencer ao NDK ou ao
  prefixo ARM64. O modelo de link do CMake e a arquitetura dos arquivos são verificados.
- `libatomic` vem do compilador Android; o prefixo do host não participa da busca por
  bibliotecas. A descoberta de VMA aceita `include` e `include/vma`, sem forçar um caminho
  no cache. O teste com configuração limpa inclui uma `libatomic` x86_64 como regressão.
- A verificação final exige Python/PKG e os módulos usados pelos validadores de patches;
  o workflow separa dependências, runtime, Python, PKG e empacotamento/assinatura.
- Testes Android existentes e preparação nativa comparada com a implementação Python.
- A comparação inclui ELF decodificado e sua recuperação quando falta no cache.
- Componentes CPU, GPU, preparação, probe, receptor, Python e PKG compilados com NDK r29.
- Validador ELF exige ARM64/Bionic, linker Android, dependências permitidas e resolução
  de símbolos fortes, incluindo extensões Python e extrator PKG.
- Sem teste em hardware Android nesta etapa. Auditoria estática de memória não garante
  que todas as necessidades de endereçamento do guest estejam cobertas no jogo real.

Não copiar endereços, patches ou hooks específicos do Bloodborne. Não mudar driver ou
readbacks da branch estável ao testar estas etapas.

## Origem e créditos

O carregador `gpu/shim/vk_driver_loader.{cpp,h}` foi adaptado, preservando a arquitetura ICD/HAL,
do Bloodborne Android, commit `2e4726530b04f76e513e232d272d386e9973c73b`:
https://github.com/ducvd89/Bloodborne-Android/blob/2e4726530b04f76e513e232d272d386e9973c73b/gpu/shim/vk_driver_loader.cpp

O carregamento ImGui sem WSI em `gpu/shim/gow3_imgui_vulkan_loader.h` adapta o
tratamento de `gpu/shim/bbport_overlay.cpp` do mesmo commit. A adaptação aceita somente
as sete funções de helpers de superfície/swapchain não usados pela apresentação AHB;
funções de renderização ausentes continuam sendo erro de inicialização. O teste executa
o carregador Vulkan real do ImGui com um driver sem WSI para reproduzir a falha anterior.

O ABI HAL segue AOSP hardware/libhardware (Apache-2.0), descrito nos comentários do carregador.
Isto não é uma integração de `libadrenotools`: utiliza diretamente drivers Android compatíveis
com o formato de pacote AdrenoTools. A futura integração dessa biblioteca é uma opção separada.

Driver: Mesa/StevenMXZ e contribuidores; fontes/receita em
https://github.com/StevenMXZ/Adreno-Tools-Drivers/tree/v37 e patches adicionais em
https://github.com/WinNative-Emu/Drivers/tree/main/patches . O pacote inclui avisos e links de origem em `gow3port/licenses/BIONIC-NOTICE.txt`;
o manifesto do driver identifica os binários exatos.
