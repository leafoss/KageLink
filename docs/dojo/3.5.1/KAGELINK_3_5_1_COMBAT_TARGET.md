# KageLink 3.5.1 — Alvo lógico persistente do combate

[English](KAGELINK_3_5_1_COMBAT_TARGET.en.md)

## Evidência física

Os vídeos `round_002_20260731_142626_16052.avi` e `round_003_20260731_143032_9892.avi` mostraram que um único adversário recebia vários `track_id` durante a mesma luta. Efeitos horizontais, oclusão pelo jogador, animações sem movimento, scrolling e um reset completo provocado por pico sustentado também interrompiam o lock.

## Arquitetura anterior

```text
movimento
→ Candidate
→ EntityTrack
→ _grid_target_id
→ decisão de combate
```

O alvo ativo era o próprio ID visual. `CONTACT_MEMORY` e `CONTACT_REBIND` reduziam perdas curtas, mas não existia uma identidade lógica separada.

## Arquitetura 3.5.1

```text
detector global
→ tracks visuais descartáveis
→ Combat Target persistente
   ├── combat_target_id estável
   ├── current_visual_track_id substituível
   ├── posição/velocidade previstas
   ├── aparência e tamanho recentes
   ├── confiança
   └── direção de contato
→ decisão PURSUIT ou MELEE_LOCK
```

Estados:

```text
VISIBLE
CONTACT
OCCLUDED_PREDICTED
LOCAL_REBIND
LOST
```

`RAW CANDIDATES = 0` por poucos frames não remove o alvo. Um novo track próximo e compatível pode ser associado ao mesmo `combat_target_id`.

## Rebind local

A pontuação padrão utiliza:

```text
45% distância até a posição prevista
25% tamanho e proporção
15% aparência
15% coerência de movimento/direção
```

A busca local ocorre antes de qualquer retorno à aquisição global. Durante `MELEE_LOCK`, candidatos distantes recebem penalidade forte e não podem roubar o alvo facilmente.

## Direção e movimentação

- `PURSUIT`: aproximação em pulsos curtos já existentes, sempre reavaliados;
- `MELEE_LOCK`: cancela perseguição contínua e preserva direção de contato;
- zona morta padrão: 12 px nos eixos horizontal e vertical;
- inversão de direção exige três observações consistentes;
- o planner usa o `combat_target_id` lógico para confirmar movimento, e não o ID visual descartável.

## Efeitos e scrolling

O tracker aplica rejeições conservadoras e configuráveis para:

```text
TOO_HORIZONTAL
TOO_VERTICAL
MAP_BORDER
HUD_REGION
CAMERA_FLOW
```

As rejeições extremas acontecem antes da criação de tracks. A compensação de câmera existente continua sendo usada na previsão e no rebind.

Durante combate ativo, `MAP_SAVE_RESYNC` passa a fazer uma ressincronização visual suave. O frame anterior e o alinhamento podem ser reiniciados, porém tracker, memória ambiental e identidade lógica são preservados.

## Configuração

Os parâmetros ficam centralizados no arquivo independente `config/kage_pilot_combat_target.json`. A separação mantém intacto o esquema público de `config/kage_pilot_dojo.json`:

```json
{
  "contact_radius": 48.0,
  "local_rebind_radius": 96.0,
  "contact_hold_seconds": 2.0,
  "local_rebind_seconds": 1.0,
  "hard_lost_timeout": 3.0,
  "target_switch_confirm_frames": 3,
  "direction_confirm_frames": 3,
  "horizontal_dead_zone": 12.0,
  "vertical_dead_zone": 12.0,
  "distance_weight": 0.45,
  "size_weight": 0.25,
  "appearance_weight": 0.15,
  "movement_weight": 0.15,
  "minimum_rebind_score": 0.48,
  "camera_flow_compensation": true,
  "structured_logging_enabled": true
}
```

## Vídeo de diagnóstico

O AVI por rodada passa a mostrar:

- Combat Target ID;
- Visual Track ID;
- estado e confiança;
- idade e tempo desde a última visão;
- posição conhecida e prevista;
- direção de contato;
- `PURSUIT` ou `MELEE_LOCK`;
- último comando;
- raio e melhor score de rebind;
- troca pendente;
- candidatos RAW, filtrados e rejeitados;
- fluxo da câmera;
- caixa prevista tracejada, região de rebind, trilha e motivos de rejeição.

A anotação é aplicada somente após a percepção e não altera frame, tracks ou decisões.

## Telemetria

Eventos estruturados incluem:

```text
target_acquired
target_visible
target_contact
target_occluded
local_rebind_started
local_rebind_success
local_rebind_failed
target_switch_proposed
target_switch_confirmed
target_lost
direction_changed
```

## Limite da validação por replay

Os dois AVI recebidos já possuem caixas, painéis e textos gravados sobre o frame. Recortar o painel principal não produz o frame RAW original e contaminaria a percepção. Por isso eles foram usados para revisão visual e correlação temporal, não como replay quantitativo definitivo do novo detector.

A comparação final de perdas, rebinds e trocas de direção precisa de novos vídeos gerados pelo Setup atualizado.

## Escopo preservado

Esta camada não altera:

- localização ou clique no Dojo Trainer;
- diálogo do sparring;
- KO pelo chat;
- leitura de HP, stamina ou chakra;
- meditação e toggles `V/Y`;
- retorno pós-combate;
- F12, Stop e liberação de teclas.

A PR continua Draft e não pode ser mesclada sem autorização explícita de Rafael.
