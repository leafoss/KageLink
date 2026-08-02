# PR26.13 — Autoridade por mudança de célula de 64 px

A PR26 permanece empilhada sobre a PR25 e mantém continuidade de alvo, replay integral, diagnóstico de falhas, grade imutável de 64 px, facing, R, pulso H, F12, KO por chat e recuperação pós-combate.

## Correção arquitetural

O cluster agregado não representa mais um inimigo e não possui autoridade para definir:

- bounding box;
- posição dos pés;
- direção;
- identidade;
- hostilidade;
- `COMBAT_LOCK`.

O cluster existe somente como **indicação espacial de busca**. Cada célula de `64x64` mantém separadamente:

```text
baseline da própria célula
imagem atual da própria célula
máscara de diferença da própria célula
changed ratio da própria célula
maior componente da própria célula
bbox do componente da própria célula
associação corpo <-> mudança da própria célula
```

Células vizinhas nunca são fundidas para criar a geometria usada pelo combate.

## Associação de corpo

Um componente de célula pode gerar atenção e orientação. Para gerar autoridade hostil, o detector bruto ou a Target Capsule deve coincidir geometricamente com o componente alterado daquela mesma célula.

```text
mudança em célula A + corpo em célula A
-> entidade vinculada

mudança em célula A + corpo em célula B
-> nenhuma identidade compartilhada
```

Uma mudança vertical sem `raw_id` não pode mais criar nem fixar `COMBAT_LOCK`. Isso impede que um NPC animado acima do jogador empreste sua identidade ao inimigo real localizado à direita.

## Direção coerente

Depois da associação, a direção e o bbox usados pelo combate vêm do corpo vinculado, não do bbox agregado do cluster. Assim, ocupação, Target Capsule e facing passam a falar do mesmo objeto.

## Sobreposição com o jogador

A exclusão retangular destrutiva foi substituída por uma cápsula central estreita de até aproximadamente `16x34 px`.

```text
antes: retângulo grande apagava jogador + inimigo sobreposto
agora: somente o núcleo central do jogador é removido
```

Pixels laterais e superiores do inimigo permanecem disponíveis quando ele chega pela esquerda, direita ou por cima.

## Baseline central

A captura pré-treinador não exclui mais uma região `3x3` em torno do jogador. Todas as células estáveis são armazenadas individualmente. Nas células atravessadas pelo jogador, somente o núcleo central é reconstruído por inpainting antes da mediana temporal.

Isso elimina a cruz permanente de células `CLASS_REFERENCE` ao redor do jogador e permite comparação exata por célula também na região central.

## Fragmentos em contato

Uma célula `WEAK` pode participar quando:

- possui baseline exata;
- contém componente real mínimo;
- um corpo bruto/Target Capsule coincide com a mesma célula.

Esse caminho recupera fragmentos do inimigo parcialmente removidos pela máscara sem transformar ruído isolado em alvo.

## Prioridade antes do latch

Antes do primeiro alvo da rodada ser fixado:

```text
corpo vinculado a mudança da mesma célula
> mudança visual sem corpo bruto
```

Depois de um `COMBAT_LOCK` válido, a continuidade PR26.9 permanece ativa até KO.

## Overlay

O replay passa a mostrar:

```text
CELL AUTHORITY: comparisons=64x64
components=<componentes independentes>
search_clusters=<grupos usados somente para busca>
cluster_lock=OFF
```

Contornos `SEARCH` mostram apenas a região sugerida pelo cluster. Os componentes de autoridade continuam individualizados por célula.

## Desempenho

Os defaults foram ajustados para reduzir pausas síncronas observadas nos replays físicos:

```text
PR24 semantic interval: 4 s
occupancy evidence save interval: 10 s
```

A comparação de pixel por célula continua ocorrendo em todos os frames; apenas a classificação semântica pesada e a escrita de pacotes PNG ficaram menos frequentes.

## Validação automática

A suíte cobre:

- duas células adjacentes permanecendo como dois componentes independentes;
- corpo bruto associado somente à célula realmente sobreposta;
- recuperação de fragmento `WEAK` apenas com corpo da mesma célula;
- cápsula do jogador preservando pixels laterais e superiores;
- inpainting restrito ao núcleo do jogador;
- contratos determinísticos da PR25 e parsing dos launchers PowerShell.

A PR permanece Draft e não deve ser mesclada antes do novo teste físico.
