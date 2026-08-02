# PR26 — Percepção por células, identidade móvel e hostilidade

Esta PR mantém a PR26 empilhada sobre a PR25.

A PR25 continua responsável por:

```text
Target Capsule + facing + chase + H
```

A PR26 somente entrega autoridade física depois de confirmar uma entidade visual, selecionar um único lock e validar hostilidade.

## Grade imutável

```text
CELL_SIZE=64x64
```

A grade não pode ser redimensionada. Diferença de pixels usa somente:

```text
EXACT_CELL_BASELINE
CLASS_REFERENCE
```

`bbox_coverage_ratio` é apenas telemetria e nunca substitui `true_changed_ratio`.

## PR26.6 — correções do teste físico

O teste da PR26.5 revelou seis falsos clusters estáticos logo no primeiro frame, principalmente faixas horizontais como `64x34`, `128x34` e `107x24`. O provável adversário real apareceu depois como um componente vertical central de aproximadamente `24x64`, com raw tracks e distância próxima ao jogador.

A PR26.6 aplica os seguintes contratos:

### Baseline limpa

```text
trainer search termina
-> diálogo ainda fechado
-> baseline capturada
-> clique no treinador
-> diálogo
-> OK
-> SpawnDelay
-> percepção
```

A baseline não é mais capturada com o diálogo aberto.

### Rejeição de artefatos

Os seguintes padrões não podem virar entidade:

```text
faixa horizontal larga e baixa
faixa superior/inferior de UI
coluna fina na borda
campo quase totalmente alterado
cluster fora do limite humanoide 2x3 / 6 células
```

### Evidência real de entidade

Persistência estática, sozinha, não confirma entidade.

`ENTITY_CONFIRMED` exige pelo menos duas evidências em três observações, baseadas em:

```text
forma vertical + raw track
raw track consistente entre frames
movimento espacial plausível
```

Depois disso, somente um track selecionado recebe `SELECTED_VISUAL_LOCK`.

### Autoridade DANGER

```text
DANGER_CONFIRMED / DANGER_LIKELY
-> podem criar autoridade DANGER

DANGER_WEAK_PRIOR
-> somente ranking/telemetria
-> nunca cria DANGER_LOCK sozinho
```

### Continuidade física rígida

Raw-ID é evidência auxiliar e nunca autoriza teleporte.

Saltos acima do limite de células/pixels calculado pelo tempo entre frames são rejeitados, mesmo quando existe raw-ID compartilhado.

### Mudança global de cenário

Quando várias células distribuídas em diferentes colunas apresentam alteração quase total simultaneamente:

```text
GLOBAL_SCENE_CHANGE
-> invalidar todas as baselines afetadas
-> apagar todos os tracks
-> bloquear toda autoridade
-> reaprender células estáveis
```

## Modos seguros

```text
PERCEPTION_ONLY
TURN/MOVE/R/H bloqueados

FACE_ONLY
somente TURN após SELECTED_VISUAL_LOCK
MOVE/R/H bloqueados

FULL_COMBAT
HOSTILE_CONFIRMED -> COMBAT_LOCK -> Target Capsule + facing + chase + H
```

## Critério do próximo teste

Executar somente `PERCEPTION_ONLY`.

A percepção será considerada aprovada quando:

```text
PR26_PRETRAINER_BASELINE acontece antes de TRAINER_CLICK_ONCE
faixas horizontais/bordas aparecem como rejeitadas
um componente vertical central chega a PR26_ENTITY_CONFIRMED
um único track chega a PR26_SELECTED_VISUAL_LOCK
nenhum salto impossível preserva identidade
nenhum TURN/MOVE/R/H é enviado
```
