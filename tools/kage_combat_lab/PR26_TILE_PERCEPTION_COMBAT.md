# PR26.16 — Cobertura de baseline e vivacidade da aquisição

A PR26 permanece empilhada sobre a PR25 e mantém a grade imutável de `64x64`, comparação individual por célula, Target Capsule, replay integral, diagnóstico de falhas, facing, R, pulso H, F12, KO por chat e recuperação pós-combate.

## Falha física corrigida

A PR26.15 impediu a migração da identidade para paredes, mas a nova rodada revelou uma falha anterior à identidade:

```text
baseline pré-luta armazenou somente 72 de 84 células
-> células centrais do spawn não receberam baseline exata garantida
-> inimigo apareceu ao lado do jogador
-> frame 11 mediu raw=(0.1,0.2), response=0.144
-> viewport estava praticamente imóvel
-> câmera foi marcada como não autoritativa
-> exact_baselines foi substituído por {}
-> todos os masks/estados de ocupação foram zerados
-> o sistema permaneceu em SEARCH até F12/timeout
```

O inimigo continuava visível no vídeo, mas a percepção havia apagado sua própria referência visual.

## Célula de 64 px continua sendo a verdade visual

Cada célula mantém individualmente:

```text
baseline exata
imagem atual
máscara de diferença
changed ratio
componente
bbox
associação com corpo atual
```

Clusters continuam sendo apenas dicas de busca. Classe semântica e igualdade de célula não criam identidade nem autoridade ofensiva.

## Baseline pré-spawn robusta

A captura antiga descartava toda a sequência de uma célula quando um único par de frames excedia a estabilidade temporal. Animação do jogador, efeitos e variação visual podiam impedir que justamente as células centrais fossem armazenadas.

A PR26.16 substitui esse comportamento por mediana temporal robusta:

```text
vários crops da mesma célula
-> remoção da silhueta completa do jogador somente durante a captura pré-spawn
-> mediana temporal por pixel
-> um frame animado não elimina toda a célula
```

A máscara ampla é usada apenas antes do inimigo nascer. Durante o combate, permanece a cápsula estreita, preservando pixels do inimigo em sobreposição.

## Cobertura local obrigatória

Todas as células disponíveis em `D<=3` do jogador pré-spawn precisam possuir baseline exata.

```text
local_D3 armazenado integralmente
-> combate pode comparar o inimigo com o piso real da própria célula

qualquer célula local ausente
-> captura falha antes do clique no treinador
-> rodada não começa cega
```

A telemetria obrigatória é:

```text
PR26_PRETRAINER_BASELINE_COVERAGE stored=<n>/<total> local_D3=<n>/<required> authority=EXACT_CELL_BASELINE
```

Referências genéricas de classe continuam úteis para semântica, mas têm autoridade zero na aquisição inicial.

## Câmera estática não apaga baseline

Resposta baixa da correlação de fase não significa necessariamente movimento. Uma arena estática com poucos detalhes pode produzir resposta baixa mesmo quando o deslocamento medido permanece próximo de zero.

Agora:

```text
response >= 0.035
E distância entre tradução bruta e tradução aceita <= 2.5 px
-> LOW_RESPONSE_STATIC_VIEWPORT_HOLD
-> mantém a última tradução aceita
-> mantém exact_baselines
-> percepção continua ativa
```

Deslocamentos grandes e pouco confiáveis, como `(-11,+29, response=0.100)`, continuam rejeitados e não recebem autoridade.

## Recuperação do corpo recém-spawnado

O detector bruto pode classificar o inimigo recém-aparecido ou sobreposto como `CONTAMINATED_ACTIVITY` antes de acumular duas observações limpas. Exigir imediatamente `body_like=True` criava um impasse: a célula enxergava mudança, mas nenhum corpo era permitido para provar que aquela mudança era o inimigo.

A PR26.16 permite promoção controlada quando todos os requisitos são satisfeitos:

```text
track bruto visível
+
geometria corporal plausível
+
bbox ou pé sobrepõe pixels alterados
+
baseline EXATA daquela célula
+
confiança ou movimento mínimo
+
track não está centrado no próprio jogador
+
componente não é terreno dominante
-> corpo atual elegível para confirmação
```

Ainda são bloqueados:

```text
mesma célula sem sobreposição de pixels
track no centro conhecido do jogador
MULTI_CELL_BLOB
campo 43x64 / 64x23
célula saturada
classe genérica sem baseline exata
cluster sem corpo
```

## Continuidade preservada

Depois de um latch legítimo:

```text
corpo atual ou Target Capsule confirmado
-> geometria pode ser atualizada

perda visual
-> identidade lógica preservada
-> Target Capsule procura D1 -> D2 -> D3
-> MOVE/H bloqueados

parede/piso/cluster raw-less
-> não pode mover a identidade
```

As proteções das PR26.14 e PR26.15 permanecem:

- `TURN_ONLY` fora do `GridFocusStrategy`;
- alvo lógico somente depois de `ROUND_TARGET_LATCHED`;
- ReID impossível antes do latch;
- pixel cluster sem autoridade de identidade;
- corpo atual obrigatório para MOVE/H;
- JSON de evento congelado no frame do gatilho.

## Validação automática

A suíte cobre especificamente:

- resposta `0.144` com deslocamento estático mantendo a baseline;
- salto `(-11,+29, response=0.100)` continuando bloqueado;
- mediana temporal ignorando um frame animado isolado;
- track bruto fraco promovido somente por sobreposição real com pixels alterados da baseline exata;
- mesma célula sem sobreposição sendo rejeitada;
- track centrado no jogador sendo rejeitado;
- contratos determinísticos da PR25;
- parsing dos launchers PowerShell.

A PR permanece Draft e não deve ser mesclada antes de uma nova rodada física no Windows confirmar a aquisição real.
