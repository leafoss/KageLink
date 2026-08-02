# PR26.3 — ocupação real por pixels e identidade móvel de `DANGER`

## Objetivo / Objective

A PR26.3 mantém a PR26 empilhada sobre a PR25, mas substitui a aquisição baseada em raw bbox e classificação momentânea por um mapa de ocupação real da grade de 64 px.

PR26.3 keeps PR26 stacked on PR25 and replaces raw-bbox/momentary classification acquisition with a real 64 px occupancy map.

```text
PR24 classifica lentamente o terreno
→ true pixel diff identifica células ocupadas
→ células adjacentes formam DANGER_CLUSTER
→ DANGER cria uma identidade móvel
→ FACE_ONLY_LOCK acompanha orientação
→ aproximação em pixels confirma hostilidade
→ HOSTILE_CONFIRMED cria COMBAT_LOCK
→ Target Capsule + facing + chase + H
```

## Regra central

```text
DANGER não pertence para sempre à célula.
DANGER cria uma identidade.

Quando a célula original volta a UNKNOWN/WALKABLE,
mas uma célula próxima passa a estar ocupada,
a identidade DANGER é transferida para o novo cluster.
```

## Verdade dos pixels

As métricas são separadas:

```text
true_changed_ratio
bbox_coverage_ratio
```

`true_changed_ratio` somente pode vir de:

```text
EXACT_CELL_BASELINE
CLASS_REFERENCE
```

`bbox_coverage_ratio` é apenas telemetria. Nunca cria ocupação, lock, facing ou autorização ofensiva.

A comparação real usa:

- diferença de cor em Lab;
- diferença de luminância;
- diferença de bordas;
- opening e closing morfológicos;
- componentes conectados;
- maior blob, largura e altura.

Thresholds iniciais:

```text
weak:    0.04
suspect: 0.08
strong:  0.12
blob mínimo: 180 px
blob forte: 250 px
largura mínima: 8 px
altura mínima: 14 px
```

## Baseline

Uma célula recebe `EXACT_CELL_BASELINE` somente após pelo menos cinco capturas estáveis por padrão.

A baseline não é aprendida quando:

- existe raw track visível sobre a célula;
- a célula é `DANGER`, `PLAYER` ou `IGNORE_DYNAMIC`;
- está próxima de um `DANGER` recém-classificado;
- existe atividade temporal acima do limite;
- a imagem diverge excessivamente da referência de terreno.

Depois de aceita, a baseline fica congelada durante a rodada.

Enquanto a baseline exata ainda não existe, é usada uma imagem real da PR24 como `CLASS_REFERENCE`, com peso reduzido. Para `DANGER` e `UNKNOWN`, o sistema procura a referência não perigosa visualmente mais próxima, em vez de escolher uma amostra arbitrária.

## Mapa de ocupação

Todas as células calibradas são comparadas em cada frame rápido, independentemente da existência de raw track.

Cada célula recebe:

```text
EMPTY
WEAK
OCCUPIED
```

E registra:

```text
true_changed_ratio
bbox_coverage_ratio
diff_source
largest_blob
edge_delta
color_delta
occupancy_score
danger_prior
persistence
```

## Clusters

Células ocupadas adjacentes são agrupadas:

```text
cabeça (7,0)
tronco (7,1)
pés   (7,2)
→ DANGER_CLUSTER {(7,0),(7,1),(7,2)}
```

A posição da entidade é o centro inferior do cluster. A célula antiga não controla mais a orientação depois que fica vazia.

Raw track IDs são evidência secundária. A identidade principal considera:

- células compartilhadas;
- distância entre foot points;
- tempo entre frames;
- velocidade máxima configurada;
- raw IDs compartilhados quando disponíveis;
- ocupação e prior de perigo.

## Propagação de `DANGER`

Uma classificação `DANGER >= 0.80` cria `DANGER_SEED`.

O seed mantém memória por condição híbrida:

```text
2,5 segundos
OU
12 frames rápidos
```

A busca de continuidade cresce de acordo com o tempo decorrido:

```text
max_jump = ceil(delta_time × max_speed_cells_per_second)
```

Quando um cluster descendente de `DANGER` entra em uma célula `UNKNOWN` ou `WALKABLE`, ele mantém seu `danger_score` e gera:

```text
PR26_DANGER_MOVED id=... from=... to=...
```

## Locks

### `ATTENTION_LOCK`

Criado pelo seed `DANGER`. Mantém memória e procura ocupação compatível.

Sem autoridade física.

### `FACE_ONLY_LOCK`

Criado após duas observações válidas dentro de três frames.

Usa o foot point atual do cluster e deadzone de 12 px.

Autoridade:

```text
TURN permitido somente no modo FACE_ONLY
MOVE bloqueado
R bloqueado
H bloqueado
```

### `COMBAT_LOCK`

A aproximação é medida em pixels. Exige inicialmente:

```text
3 reduções nas últimas 5 observações
redução total >= 32 px
```

Depois, contato em `D<=1` ou dentro da distância física configurada confirma:

```text
HOSTILE_CONFIRMED
→ COMBAT_LOCK
```

Somente em `FULL_COMBAT` o candidato é enviado à PR25.

## Modos de segurança

### `PERCEPTION_ONLY` — padrão

```text
TURN bloqueado
MOVE bloqueado
R bloqueado
H bloqueado
```

Serve para validar pixels, clusters e propagação sem risco de movimento.

### `FACE_ONLY`

```text
TURN permitido
MOVE bloqueado
R bloqueado
H bloqueado
```

Serve para validar a orientação antes do combate.

### `FULL_COMBAT`

Disponível explicitamente, mas não deve ser utilizado até os dois modos anteriores serem aprovados fisicamente.

## Pipeline lento e rápido

```text
PR24 semantic classification: aproximadamente 1 vez por segundo
pixel occupancy / clusters / tracking: em todos os frames do runtime
```

A PR24 cria ou reforça seeds. O tracking rápido não depende de reclassificação semântica em cada frame.

## Evidências

A cada intervalo configurado, as cinco células mais relevantes são salvas em:

```text
kage_pilot_loop_logs/occupancy_evidence/frame_XXXXXX/
```

Arquivos:

```text
cell_x_y_baseline.png
cell_x_y_current.png
cell_x_y_diff.png
cell_x_y_mask.png
overlay.png
metadata.json
```

O `metadata.json` registra classe, confiança, origem do diff, `true_changed_ratio`, cobertura da bbox, blob, ocupação e prior de perigo.

## Preflight

```powershell
.\run_pr26_tile_combat.ps1 -PreflightOnly
```

Valida:

- grade imutável de 64 px;
- calibração e conhecimento PR24;
- exemplos `DANGER`;
- imagens reais de referência;
- thresholds de pixels e blobs;
- memória móvel de perigo;
- modo físico selecionado.

## Primeira validação física

```powershell
.\run_pr26_tile_combat.ps1 `
  -PerceptionOnly `
  -Rounds 1 `
  -CombatSeconds 60 `
  -PostCombatTimeout 240 `
  -DialogDelay 5 `
  -SpawnDelay 5 `
  -TrainerSearchTimeout 90 `
  -HostilityOverlay
```

O personagem não pode enviar nenhuma tecla de combate. Avaliar:

```text
PR26_DANGER_SEED
PR26_DANGER_MOVED
PR26_OCCUPANCY_STATE
PR26_MOBILE_DANGER
PR26_EVIDENCE_SAVED
```

Critérios:

- chão estável próximo de zero;
- inimigo com máscara conectada;
- `true_changed_ratio` diferente de `bbox_coverage_ratio`;
- cluster acompanhando o inimigo;
- identidade mantida após `DANGER → UNKNOWN/WALKABLE`;
- célula antiga vazia não controlando o foot point.

## Segunda validação física

Somente após aprovação do modo anterior:

```powershell
.\run_pr26_tile_combat.ps1 `
  -FaceOnly `
  -Rounds 1 `
  -CombatSeconds 60 `
  -PostCombatTimeout 240 `
  -DialogDelay 5 `
  -SpawnDelay 5 `
  -TrainerSearchTimeout 90 `
  -HostilityOverlay
```

Aceitação:

- orientação correta em pelo menos 90% das observações válidas;
- nenhum MOVE, R ou H;
- ambiguidade bloqueia o giro;
- o facing usa o cluster atual, não a célula original.

## Contratos preservados

```text
1 célula = 64 × 64 px
pulso de aproximação PR25 = 100 ms
pulso H = 50 ms
cooldown H = 5 s
F12 como parada imediata
KO pelo chat
Trainer day/night
meditação mínima de 5,25 s
fluxo pós-combate
```

## Testes

A suíte inclui:

- bbox grande com pixels iguais produz `true_changed_ratio=0`;
- `bbox_coverage_ratio` nunca vira diferença de pixels;
- `DANGER → UNKNOWN ocupado` transfere a identidade;
- troca de raw track ID não destrói o cluster;
- `PERCEPTION_ONLY` nunca exporta candidato;
- `FACE_ONLY` bloqueia ações não relacionadas ao giro;
- `FULL_COMBAT` aguarda aproximação e contato;
- candidatos sintéticos negativos permanecem sem autoridade.
