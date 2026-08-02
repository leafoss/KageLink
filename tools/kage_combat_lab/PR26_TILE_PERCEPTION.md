# PR26 — percepção de tiles da PR24 integrada ao combate da PR25

## Objetivo

A PR26 nasce diretamente da branch da PR25 e usa o conhecimento visual persistente criado pela PR24 para melhorar a aquisição inicial do inimigo.

```text
PR24: tile 64 px + conhecimento de terreno
PR25: raw tracks + Target Capsule + ReID + facing + combate
PR26: tile desconhecida vira evidência autoritativa de aquisição
```

Não existe shadow mode nesta PR. Se a calibração ou o conhecimento da PR24 não estiverem disponíveis, o processo falha antes de armar o combate.

## Fluxo físico

```text
captura do HWND do jogo
→ arena da PR25
→ grade imutável de 64 px
→ descritor visual compatível com a PR24
→ comparação somente contra exemplos ensinados de terreno
→ tile conhecida: reforça background e rejeita tracks fracos
→ tile desconhecida: promove track fraco ou cria track sintético por atividade temporal
→ ATTENTION por duas evidências
→ Target Capsule cria a identidade lógica
→ candidatos sintéticos são desligados
→ PR25 continua com ReID, orientação, chase e H autorizado
```

## Fontes de conhecimento aceitas

A PR26 lê os mesmos arquivos persistidos pela PR24:

```text
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>\calibrations\<region>_grid.json
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>\tile_knowledge\<region>.json
```

Somente classes de terreno são usadas como baseline:

- `walkable`
- `wall`
- `walkable_with_jutsu`
- `blocking_object`
- `transition`
- `danger`

`player`, `npc` e `ignore_dynamic` não são tratados como terreno, portanto não escondem uma entidade viva durante a aquisição.

## Regras de autoridade

### Durante aquisição

Uma tile desconhecida pode:

1. promover um raw track visível de baixa confiança para `CLEAN_BODY` quando houver forma, movimento ou atividade temporal suficiente;
2. gerar um track sintético estável quando nenhum raw track existir, mas houver uma região móvel dentro da tile desconhecida.

A estratégia da PR25 continua exigindo duas evidências antes do lock.

### Depois da Target Capsule

Quando `target_memory.ready` se torna verdadeiro:

- nenhum novo track sintético é criado;
- aparência, posição prevista, forma, movimento e memória negativa voltam a dominar;
- ReID local permanece com a PR25;
- a tile continua enriquecendo/rejeitando raw tracks, mas não substitui a identidade lógica.

## Contratos preservados

```text
1 célula lógica = 64×64 pixels
RIGHT após OK = um único pulso
R baseline durante SEARCH/ATTENTION/ReID
H somente com alvo e facing autorizados
F12 libera todas as teclas
KO autoritativo pelo chat
meditação com intervalo mínimo de 5,25 s entre os dois usos de V
Trainer day-64 e night-64
```

## Teste PowerShell

Na pasta `tools\kage_combat_lab`:

```powershell
.\run_pr26_tile_combat.ps1 -PreflightOnly
```

O preflight confirma:

- os dois arquivos da PR24 existem;
- a calibração usa exatamente 64 px;
- há pelo menos um exemplo de terreno;
- os thresholds serão enviados ao processo de combate.

Primeiro teste físico, uma rodada:

```powershell
.\run_pr26_tile_combat.ps1 `
  -Rounds 1 `
  -CombatSeconds 120 `
  -PostCombatTimeout 240 `
  -DialogDelay 5 `
  -SpawnDelay 5 `
  -TrainerSearchTimeout 90
```

Durante a luta, procurar linhas como:

```text
PR26 TILE PERCEPTION: ACTIVE and authoritative during acquisition
PR26_TILE_SCAN cells=... unknown=... active_unknown=... synthetic=... capsule_ready=False
```

O comportamento esperado é:

```text
spawn do inimigo
→ active_unknown aumenta
→ raw track é promovido ou synthetic=1
→ ATTENTION
→ LOCKED
→ capsule_ready=True
→ synthetic volta para 0
```

Use F12 imediatamente se o alvo adquirido for cenário, efeito ou o próprio jogador.

## Ajustes disponíveis

```powershell
-SimilarityThreshold 0.90
-NoveltyThreshold 0.12
-ActivityThreshold 0.018
-TerrainRejectSimilarity 0.965
```

Interpretação:

- `SimilarityThreshold` maior torna mais tiles desconhecidas;
- `NoveltyThreshold` maior exige diferença mais forte para ajudar a aquisição;
- `ActivityThreshold` maior exige movimento visual mais forte para criar candidato sintético;
- `TerrainRejectSimilarity` menor rejeita mais agressivamente tracks sobre terreno conhecido.

## Validação determinística

Os testes cobrem:

- promoção de raw track fraco em tile desconhecida;
- rejeição de falso track sobre terreno conhecido;
- criação de candidato sintético por mudança temporal;
- interrupção dos candidatos sintéticos após a Target Capsule assumir;
- parsing dos dois launchers PowerShell.
