# PR26.5 — afinidade semântica `DANGER` e aquisição visual por baseline exata

Este trabalho mantém a PR26 empilhada sobre a PR25, especificamente sobre `agent/pr25-kage-combat-lab-64px`, permanece Draft e não altera os contratos físicos validados da PR25.

## Falha física corrigida

O log da PR26.4 mostrou simultaneamente:

```text
occupied=3 clusters=3
danger=0 unknown=81
cluster=None
reason=no mobile DANGER identity
```

A diferença real de pixels encontrava entidades visuais, mas nenhum cluster podia receber identidade porque `DANGER` ainda era um requisito obrigatório.

## Nova regra

```text
DANGER = prioridade forte, não requisito absoluto para reconhecer entidade
```

Cada scan semântico agora preserva, mesmo quando a classe final é `UNKNOWN`:

```text
best_category
best_similarity
danger_similarity
best_non_danger_similarity
danger_margin
```

Níveis iniciais:

```text
DANGER_CONFIRMED: danger_similarity >= 0.90 e classe final DANGER
DANGER_LIKELY:    danger_similarity >= 0.82 e danger_margin >= 0.04
DANGER_WEAK:      danger_similarity >= 0.72
```

Esses níveis não confirmam hostilidade. Eles apenas priorizam clusters que já possuem foreground real.

## Dois caminhos de lock visual

### `DANGER_LOCK`

Criado quando um cluster com `EXACT_CELL_BASELINE` recebe afinidade `DANGER` atual ou herdada.

### `ENTITY_LOCK`

Criado sem classificação perfeita de `DANGER` quando o cluster possui:

```text
EXACT_CELL_BASELINE
componente real de pixels
máscaras conectadas cardinalmente
geometria máxima de 2x3 células / 6 células
forma plausível
persistência de 2 observações em 3
```

`ENTITY_LOCK` acompanha a entidade para validação de comportamento. Ele não autoriza ataque.

## Autoridade ofensiva

```text
DANGER_LOCK ou ENTITY_LOCK
→ observar distância em pixels
→ aproximação autônoma consistente
→ HOSTILE_PROBABLE
→ contato confirmado
→ HOSTILE_CONFIRMED
→ COMBAT_LOCK
```

Somente `COMBAT_LOCK` no modo `FULL_COMBAT` entrega o candidato à PR25.

## Baseline antes do OK

A baseline exata agora é capturada com o diálogo validado ainda aberto:

```text
diálogo confirmado
→ bloquear toda entrada física
→ capturar baseline limpa
→ salvar baseline temporária
→ clicar no OK validado
→ manter SpawnDelay normal
→ inimigo nasce
→ processo filho carrega baseline pré-OK
```

Assim, o inimigo não pode ser incorporado à referência de chão durante a janela de spawn.

## Isolamento de desempenho

Em `PERCEPTION_ONLY` e `FACE_ONLY`, o detector de templates do treinador é suspenso durante o runtime de percepção. A busca do treinador continua ativa no processo externo antes da luta. Em `FULL_COMBAT`, o retorno pós-KO continua preservado.

## Telemetria por cluster

Cada cluster gera:

```text
PR26_CLUSTER_CANDIDATE
local_id
cells
bbox
foot point
true_changed_ratio
occupancy_score
danger_level
danger_similarity
danger_margin
raw track IDs
distance to player
persistence
```

Legenda do overlay:

```text
DC = DANGER_CONFIRMED
DL = DANGER_LIKELY
DW = DANGER_WEAK_PRIOR
-- = nenhuma afinidade DANGER
```

O cabeçalho informa se o ativo é `DANGER_LOCK` ou `ENTITY_LOCK`.

## Modos de segurança

```text
PERCEPTION_ONLY: TURN/MOVE/R/H bloqueados
FACE_ONLY: TURN somente após lock validado; MOVE/R/H bloqueados
FULL_COMBAT: HOSTILE_CONFIRMED obrigatório para COMBAT_LOCK
```

IDs sintéticos negativos e candidatos apenas de tile continuam sem autoridade ofensiva.

## Validação automática

```text
139 testes pytest
15 cenários determinísticos da PR25
parsing dos dois launchers PowerShell
```

Os testes novos cobrem:

- `UNKNOWN` mantendo `DANGER_LIKELY`;
- `UNKNOWN` mantendo `DANGER_WEAK_PRIOR`;
- prioridade completa para `DANGER_CONFIRMED`;
- cluster humanoide com baseline exata elegível a `ENTITY_LOCK`;
- `CLASS_REFERENCE` inelegível;
- cluster grande demais inelegível;
- suspensão do treinador em `PERCEPTION_ONLY`;
- preservação do treinador em `FULL_COMBAT`;
- captura pré-OK e SpawnDelay pós-OK preservado.

## Próxima validação física

Executar somente:

```powershell
.\run_pr26_tile_combat.ps1 `
  -PerceptionOnly `
  -Rounds 1 `
  -CombatSeconds 30 `
  -PostCombatTimeout 240 `
  -DialogDelay 5 `
  -SpawnDelay 5 `
  -TrainerSearchTimeout 90 `
  -HostilityOverlay
```

Critérios:

```text
PR26_PREOK_BASELINE complete antes de DOJO_DIALOG_OK_CLICKED
PR26_PREOK_BASELINE_LOADED depois do spawn
PR26_CLUSTER_CANDIDATE para os clusters reais
pelo menos um cluster persistente chegando a PR26_DANGER_LOCK ou PR26_ENTITY_LOCK
zero TURN/MOVE/R/H
```
