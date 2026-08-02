# PR26.1 — PR24 PERIGO → validação de hostilidade → combate PR25

## Objetivo / Objective

A PR26.1 mantém a PR26 empilhada sobre a PR25, mas remove a autoridade ofensiva da antiga regra `UNKNOWN + atividade = CLEAN_BODY`.

PR26.1 keeps PR26 stacked on PR25 and removes offensive authority from the former `UNKNOWN + activity = CLEAN_BODY` rule.

```text
PR24 classifica a célula / classifies the tile
→ DANGER/PERIGO é evidência visual passiva
→ um raw track positivo confirma que existe uma entidade
→ VISUAL_LOCK acompanha sem perseguir
→ a tendência de D confirma aproximação autônoma
→ HOSTILE_CONFIRMED cria COMBAT_LOCK
→ somente então PR25 recebe o candidato
→ Target Capsule + facing + chase + H
```

A distinção central é:

```text
PERIGO != INIMIGO
ENTIDADE != HOSTIL
VISUAL_LOCK != COMBAT_LOCK
```

## Falha física corrigida / Corrected physical failure

Nos primeiros testes físicos, uma área de chão/efeito foi transformada em candidato sintético negativo, recebeu tratamento equivalente a corpo limpo e contaminou o lock para a esquerda.

The first physical tests allowed floor/effect activity to become a negative synthetic candidate, behave like a clean body and contaminate the left-side lock.

A PR26.1 bloqueia esse caminho no runtime físico:

- tiles não criam candidatos ofensivos;
- `track_id < 0` nunca chega à Target Capsule;
- `track_id < 0` nunca autoriza ATTENTION, giro, chase ou H;
- `PR24CombatTilePerception.enrich_candidates()` não é chamado pelo runtime físico;
- somente raw tracks positivos podem entrar no gate de hostilidade.

## Origem calibrada da grade / Calibrated grid origin

A calibração da PR24 salva offsets no quadro completo:

```json
{
  "tile_size_px": 64,
  "offset_x_px": 0,
  "offset_y_px": 0
}
```

Os tracks da PR25 usam coordenadas relativas à arena. A PR26.1 converte os offsets antes de classificar ou calcular células:

```text
arena_origin_x = (offset_x_px - arena_rect.x) mod 64
arena_origin_y = (offset_y_px - arena_rect.y) mod 64
```

A mesma origem é usada para:

- célula do jogador;
- célula âncora do raw track;
- crops classificados pela PR24;
- histórico de distância D.

Isso impede que a classificação `PERIGO` e o candidato discordem sobre esquerda/direita.

## Estados

### `TERRAIN_ONLY`

Somente terreno ou ruído. Sem lock e sem ação.

### `DANGER_CANDIDATE`

A PR24 classificou a célula como `danger` com confiança suficiente, mas ainda existe apenas uma observação.

Sem giro, chase ou H.

### `ENTITY_SUSPECT`

Existe um raw track positivo e diferença estrutural relevante sobre terreno conhecido.

Sem giro, chase ou H.

### `ENTITY_CONFIRMED`

A entidade persistiu por pelo menos dois frames coerentes.

Cria `VISUAL_LOCK` passivo. Ainda não cria `COMBAT_LOCK`.

### `OBSERVE_HOSTILITY`

O jogador permanece sem perseguir. O gate acompanha o candidato e registra `D_history`.

### `HOSTILE_PROBABLE`

Foram observadas três reduções coerentes de distância nas últimas quatro transições.

Continua sem autoridade ofensiva até contato próximo.

### `HOSTILE_CONFIRMED`

Confirmado quando:

- a entidade visível chega autonomamente a `D=0`; ou
- chega a `D<=1` após pelo menos uma redução de distância.

Somente aqui é criado `COMBAT_LOCK`.

### `NON_AGGRESSIVE_ENTITY`

A entidade persistiu visualmente, mas a distância permaneceu estável durante aproximadamente três segundos.

Pode representar NPC, jogador neutro, objeto animado ou perigo não agressivo. Não é enviada à PR25.

## Diferença estrutural / Structural difference

Uma entidade sobre terreno conhecido é avaliada por:

- `changed_pixel_ratio`;
- maior componente conectado;
- largura e altura do blob;
- diferença de bordas;
- similaridade estrutural;
- persistência temporal;
- posição do centroide;
- continuidade espacial.

Thresholds iniciais:

```text
changed_ratio suspect: 0.08
changed_ratio strong:  0.12
largest blob suspect:  180 px
largest blob strong:   250 px
minimum blob:          8 x 14 px
strong minimum height: 18 px
persistence:           2 frames
```

O percentual sozinho nunca confirma uma entidade. Ruído espalhado sem massa conectada é rejeitado.

## Memória e continuidade

O gate mantém uma memória temporária por entidade:

- raw track atual;
- última célula;
- centroide;
- bbox;
- persistência;
- classe PR24 e confiança;
- métricas estruturais;
- `D_history`;
- estado de entidade;
- estado de hostilidade;
- `VISUAL_LOCK` e `COMBAT_LOCK`.

Mudanças de raw track podem ser reatadas somente quando a nova observação está em célula próxima e centroide coerente. Memórias suspeitas expiram após o TTL configurado.

## Target Capsule

A Target Capsule recebe somente candidatos retornados por:

```text
snapshot.combat_lock == True
```

Antes disso, a lista enviada à PR25 é vazia. Portanto:

- `ENTITY_CONFIRMED` não cria Target Capsule;
- `OBSERVE_HOSTILITY` não cria Target Capsule;
- `HOSTILE_PROBABLE` não cria Target Capsule;
- tiles e candidatos sintéticos nunca criam Target Capsule;
- somente `HOSTILE_CONFIRMED` libera o raw track positivo para a PR25.

O candidato liberado mantém seu `track_id` positivo e recebe normalização para `CLEAN_BODY` somente depois da confirmação comportamental.

## Contratos físicos preservados

Não foram alterados:

```text
1 célula = 64 x 64 px
pulso de aproximação = 100 ms
pulso H = 50 ms
cooldown H = 5 s
lógica física de R
facing authority e transação de giro
F12 como parada imediata
KO autoritativo pelo chat
Trainer day/night
meditação com intervalo mínimo de 5,25 s
fluxo pós-combate
```

## Telemetria

Exemplos:

```text
PR26_TILE_SCAN full_origin=(x,y) arena_origin=(x,y) cells=... danger=... unknown=... synthetic=0 synthetic_authority=BLOCKED

PR26_TILE_CLASS cell=(x,y) class=DANGER confidence=0.97 changed_ratio=0.240 largest_blob=900 bbox=24x52

PR26_ENTITY_STATE track=12 cell=(8,2) state=ENTITY_CONFIRMED persistence=2 source=PR24_DANGER_PLUS_STRUCTURE

PR26_HOSTILITY_OBSERVE track=12 D_history=5,4,3 approach_votes=2 retreat_votes=0 state=OBSERVE_HOSTILITY

PR26_HOSTILITY_CONFIRMED track=12 D=0 reason=visible entity reached D=0 autonomously

PR26_NON_AGGRESSIVE track=15 observed_seconds=3.20 reason=DISTANCE_STABLE

PR26_SYNTHETIC_BLOCKED track=-1000007 reason=SYNTHETIC_CANDIDATES_CANNOT_ACQUIRE_COMBAT_TARGET
```

Os JSONL de combate incluem:

- `visual_lock`;
- `combat_lock`;
- `entity_state`;
- `hostility_state`;
- `danger_confidence`;
- `terrain_class`;
- `changed_ratio`;
- `largest_blob`;
- `D_history`;
- `approach_votes`;
- `retreat_votes`;
- offsets PR24 de quadro completo e arena.

## Overlay de evidência

Use:

```powershell
-HostilityOverlay
```

O overlay é aplicado aos vídeos de evidência e mostra:

- células `danger`/`unknown`;
- classe e confiança;
- `VISUAL_LOCK`;
- `COMBAT_LOCK`;
- estado da entidade;
- estado de hostilidade;
- histórico de D.

## Gravação no encerramento

O diretório é criado ao iniciar o recorder:

```text
kage_pilot_loop_logs\event_videos\round_001
```

No `close()` — incluindo o `finally` executado após F12 — o buffer circular atual é salvo como:

```text
*_F12_OR_SESSION_STOP.mp4
*_F12_OR_SESSION_STOP.json
```

O JSON inclui os offsets de calibração e o último snapshot de hostilidade.

## Preflight

```powershell
.\run_pr26_tile_combat.ps1 -PreflightOnly
```

O preflight valida:

- grade exatamente 64 px;
- offsets PR24;
- conhecimento persistido;
- pelo menos um exemplo de terreno;
- pelo menos um exemplo `danger`;
- thresholds estruturais e de hostilidade;
- persistência mínima de dois frames;
- candidatos sintéticos sem autoridade ofensiva.

## Teste físico de uma rodada

```powershell
.\run_pr26_tile_combat.ps1 `
  -Rounds 1 `
  -CombatSeconds 120 `
  -PostCombatTimeout 240 `
  -DialogDelay 5 `
  -SpawnDelay 5 `
  -TrainerSearchTimeout 90 `
  -HostilityOverlay
```

Comportamento esperado:

```text
spawn
→ PR24 encontra DANGER
→ raw track positivo persiste
→ ENTITY_CONFIRMED
→ VISUAL_LOCK=True e COMBAT_LOCK=False
→ nenhum TURN/MOVE/H durante observação
→ D diminui porque o inimigo se aproxima sozinho
→ HOSTILE_CONFIRMED em D<=1/D=0
→ COMBAT_LOCK=True
→ PR25 adquire, alinha, persegue e usa H
```

Use F12 caso qualquer ação ofensiva apareça antes de `COMBAT_LOCK=True`.

## Testes determinísticos

A cobertura inclui:

- ruído de chão rejeitado;
- `danger` não tratado automaticamente como inimigo;
- persistência criando apenas lock visual;
- três reduções gerando `HOSTILE_PROBABLE` sem combate;
- `D<=1` após aproximação gerando `HOSTILE_CONFIRMED`;
- `D=0` confirmando hostilidade;
- NPC parado tornando-se não agressivo;
- tile `danger` sem raw track produzindo zero candidatos;
- track positivo oculto da PR25 até `COMBAT_LOCK`;
- track negativo nunca encaminhado;
- transformação dos offsets PR24 do quadro completo para a arena;
- restauração do método da Target Capsule e da origem do observer;
- gravação do buffer no encerramento;
- invariantes de 64 px, movimento, R e H preservadas.
