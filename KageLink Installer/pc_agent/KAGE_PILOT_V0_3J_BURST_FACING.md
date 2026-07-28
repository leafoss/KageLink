# Kage Pilot v0.3j — Correção de orientação durante partículas

**Data:** 28/07/2026  
**Status:** validada em rodada real e promovida ao comando canônico  
**Baseline atual:** v0.3j

## Problema observado

Uma rodada completa anterior terminou com sucesso, mas o combate demorou muito porque o inimigo passou para baixo do jogador enquanto o personagem permaneceu olhando para cima.

O log mostrou que a percepção já havia corrigido sua decisão:

```text
FACE_UP
→ MOVE_DOWN
→ FACE_DOWN
```

Entretanto, o `MotionBurstGuard` estava em `MOTION_BURST_HOLD`. A política anterior bloqueava:

- movimento;
- `H`;
- pulsos de orientação.

Como `R` continuava ativo, o personagem atacava automaticamente na direção física antiga.

## Correção v0.3j

Durante `MOTION_BURST_HOLD`, a v0.3j pode autorizar **um único pulso de orientação** quando todas as condições abaixo forem verdadeiras:

1. estado lógico `MELEE`;
2. distância de grade `d <= 1`;
3. navegação solicitada `FACE_UP`, `FACE_DOWN`, `FACE_LEFT` ou `FACE_RIGHT`;
4. alvo com autoridade visual atual:
   - `VISIBLE`;
   - `OCCLUDED`;
   - `CONTACT_REBIND`;
5. mesmo alvo e mesma direção confirmados por dois frames;
6. nenhum pulso já enviado para aquela combinação de alvo/direção durante o episódio atual de burst.

Telemetria da exceção, quando necessária:

```text
safety=BURST_FACE_CORRECT
face_pulse=down
held=r
move_pulse=-
H_WAIT
```

## O que continua bloqueado

A exceção não libera:

- perseguição;
- pulso de movimento;
- `H`;
- alvo distante;
- `CONTACT_MEMORY` sem confirmação visual atual;
- repetição contínua da direção.

Os estados abaixo continuam absolutos:

```text
MAP_SAVE_RESYNC
H_SETTLE_HOLD
```

Em `MAP_SAVE_RESYNC`, todas as teclas continuam desligadas.

## Relação com o MotionBurstGuard

A proteção não foi removida nem teve seus thresholds reduzidos. Ela continua impedindo perseguição e habilidade durante excesso de partículas.

A mudança reconhece apenas que, no corpo a corpo visualmente confirmado, manter o personagem olhando na direção errada por dezenas de segundos é mais prejudicial do que enviar um pulso cardinal já usado normalmente para orientação.

## Validação realizada

A rodada real posterior da v0.3j confirmou:

- combate considerado excelente pelo usuário;
- orientação e ataque funcionando de forma estável;
- nenhum movimento de perseguição liberado pelo novo estado;
- nenhum `H` autorizado pela exceção de orientação;
- clique único no treinador;
- KO reconhecido pelo chat;
- retorno ao treinador;
- `Y` ligado e desligado corretamente durante recuperação;
- `ROUND 1: COMPLETE`.

A amostragem de telemetria impressa não registrou necessariamente uma linha `BURST_FACE_CORRECT`, pois o cenário pode ter sido resolvido por pulsos normais entre os períodos de bloqueio. A lógica estreita da exceção permanece coberta pelos testes direcionados.

## Arquivos

```text
kage_pilot_live_v03j_round.py
kage_pilot_loop_v03j.py
tests/test_kage_pilot_v03j_burst_facing.py
```

## Situação de release

A v0.3j foi promovida para:

```text
kage_pilot_dojo.py
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
```

Antes do merge ainda são obrigatórios a suíte completa no Windows, três rodadas consecutivas pelo comando canônico e a aprovação explícita de Rafael.
