# Kage Pilot v0.3j — Correção de orientação durante partículas

**Data:** 28/07/2026  
**Status:** candidato para validação real; ainda não promovido ao comando canônico  
**Base preservada:** v0.3i

## Problema observado

Uma rodada completa terminou com sucesso, mas o combate demorou muito porque o inimigo passou para baixo do jogador enquanto o personagem permaneceu olhando para cima.

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

Como `R` continuava ativo, o personagem atacava automaticamente, mas na direção antiga.

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

Saída esperada:

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

## Arquivos

```text
kage_pilot_live_v03j_round.py
kage_pilot_loop_v03j.py
tests/test_kage_pilot_v03j_burst_facing.py
```

## Validação necessária

Antes de promover a v0.3j para `kage_pilot_dojo.py`:

- [ ] testes direcionados finalizam em `OK`;
- [ ] suíte completa finaliza em `OK`;
- [ ] uma rodada real mostra `BURST_FACE_CORRECT` quando a direção muda durante partículas;
- [ ] o personagem vira para o inimigo;
- [ ] nenhum movimento de perseguição é liberado pelo novo estado;
- [ ] nenhum `H` é disparado pelo novo estado;
- [ ] `MAP_SAVE_RESYNC` continua com `held=-`;
- [ ] loop termina em `ROUND 1: COMPLETE`;
- [ ] promoção para o comando canônico somente depois da validação real.

## Decisão de release

A v0.3i continua sendo a baseline validada. A v0.3j é uma correção aditiva e isolada. Depois de aprovada no jogo, o ponto de entrada público poderá ser atualizado para usar a v0.3j e a documentação de release candidate será ajustada.
