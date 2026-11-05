# Otimizações comparadas com o BACHATA 0.2.5

Referências: APK `bachatas4-0.2.5-release(1).apk` (runtime nativo SHA-256
`147fd32524cbf21c8946c6e93bd6e3d50ed325251aa4acae5a284f456ce6a9f4`) e
[fonte pública ARM64](https://github.com/zenithblue-oss/shadps4-arm64).
O binário distribuído contém mudanças posteriores à fonte pública; não são tratados
como revisões idênticas. A integração mantém os componentes atuais do Port.

## Walker SRT ARM64

O Port compila seu próprio bytecode SRT em instruções ARM64. Mantém os offsets
dinâmicos, operações aritméticas, máscara de ponteiros e as pilhas do interpretador.
Não substitui o compilador de shaders pelo código mais antigo da referência.

O objeto serializado continua do tamanho de um ponteiro e o cache continua contendo
o bytecode original. As instruções nativas são recriadas no carregamento. Falhas de
alocação/proteção ou operações não compiláveis usam o interpretador. Uma falha de
acesso durante execução nativa usa a recuperação já existente do runtime, desativa
o código nativo daquele programa e repete pelo interpretador. `GOW3_SRT_NATIVE=0`
permite comparar com o caminho anterior.

## Intervalos do shader de cópia

O shader HLE preserva o agrupamento de 64 KiB e o despacho MultiCopy existente.
Os uploads e as marcações de bytes modificados pela GPU passam a considerar a união
dos intervalos realmente usados, sem preencher os espaços entre eles. O rastreador
continua operando por páginas; páginas compartilhadas não são enviadas duas vezes.
Os locks são adquiridos na ordem dos endereços, uma vez por região, e a proteção de
escrita da GPU só é instalada depois de preparar os uploads.

## Cache do driver Vulkan

No Android, quando `pipeline_binary` não fornece a chave global necessária à
persistência existente, o cache tradicional do driver é carregado e salvo em
`cache/<jogo>/driver-v1/<identidade>/`. Não duplica a persistência por pipeline binary.
Os snapshots incluem os caches dos workers, sem interromper a compilação para fazer
um merge. Checkpoints ocorrem em thread de baixa prioridade a cada 30 segundos e
no encerramento normal. Merges e snapshots compartilham um mutex; o worker termina
antes da destruição dos objetos Vulkan.

Fabricante, GPU, versão do driver, UUID, tamanho, cabeçalho Vulkan e checksum são
validados. Arquivos inválidos são ignorados; falha na restauração cria cache vazio.
As gravações usam arquivo temporário e rename. `GOW3_DRIVER_CACHE=0` desativa esse
complemento; o controle existente de cache de pipelines também é respeitado.
Uma instalação limpa começa sem esse cache e o cria durante o uso.

## Resoluções

Retiradas as quatro opções experimentais 21:9, seus patches, ajustes de apresentação
e testes exclusivos. As resoluções 16:9 anteriores, incluindo 900p, permanecem.
Nenhuma configuração de readback ou seleção de driver foi alterada.

## Validação

`tests/test_android_bachata_optimizations.py` compila os helpers C++ e executa as
instruções geradas no Unicorn ARM64 2.1.4, cobrindo todas as operações aritméticas,
offsets dinâmicos, ponteiros aninhados e preservação de registradores/stack. Também
testa recuperação de SIGSEGV, compatibilidade da representação em cache, arquivos
corrompidos/incompatíveis, substituição de snapshots e locks de páginas compartilhadas.
O workflow Bionic instala a dependência de teste e executa essas verificações antes
da compilação do runtime. A compilação completa e o teste em aparelho continuam
necessários; os testes de código não estabelecem ganho de FPS medido.
