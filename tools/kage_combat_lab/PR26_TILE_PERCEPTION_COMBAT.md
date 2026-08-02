# PR26.14 — Integridade de câmera, orientação e alvo lógico

A PR26 permanece empilhada sobre a PR25 e mantém a grade imutável de `64x64`, comparação individual por célula, Target Capsule, replay integral, diagnóstico de falhas, facing, R, pulso H, F12, KO por chat e recuperação pós-combate.

## Falha física corrigida

O replay da PR26.13 demonstrou esta sequência:

```text
uma célula encontrou o corpo real
-> a correlação de câmera aceitou um salto falso de (-11,+29) com response=0.100
-> a continuidade espacial foi quebrada
-> TURN_ONLY foi entregue à estratégia como CLEAN_BODY
-> a estratégia criou logical_target_id sem COMBAT_LOCK
-> o alvo falso entrou em OCCLUDED_COAST e REID_LOCAL
-> a barreira física bloqueou MOVE/H
-> o personagem ficou parado até timeout
```

A PR26.14 corrige cada transição separadamente. Não depende de afrouxar ou apertar um único threshold.

## Unidade de verdade visual

O contrato da PR26.13 permanece:

```text
CÉLULA 64x64
-> baseline própria
-> imagem atual própria
-> máscara de diferença própria
-> changed ratio próprio
-> maior componente próprio
-> bbox próprio
-> associação corpo <-> mudança própria
```

Clusters continuam sendo apenas **dicas de busca**. Eles não possuem autoridade para bbox, posição dos pés, direção, identidade, hostilidade ou `COMBAT_LOCK`.

## Estabilidade de câmera

A correlação de fase bruta não desloca mais imediatamente a baseline congelada.

Regras:

```text
response < 0.16
-> tradução rejeitada
-> baseline anterior preservada
-> autoridade visual bloqueada naquele frame

correção pequena <= 4 px e resposta suficiente
-> pode ser aceita imediatamente

tradução significativa
-> precisa aparecer de forma consistente em 2 ou 3 observações

salto grande com confiança baixa
-> rejeitado como aceleração implausível
```

A telemetria registra:

```text
PR26_CAMERA_STABILITY
raw=(dx,dy)
accepted=(dx,dy)
response=...
authoritative=...
reason=...
```

O caso físico `raw=(-11,+29) response=0.100` agora mantém a tradução anterior e retorna `authoritative=false`.

## Separação entre orientação e combate

`TURN_ONLY` não é mais representado como `CandidateObservation` adquirível.

Antes:

```text
face_only_lock
-> CLEAN_BODY enviado ao GridFocusStrategy
-> ATTENTION
-> LOCKED
-> logical_target_id criado
```

Agora:

```text
componente compacto próximo
-> orientation_hint separado
-> pulso físico isolado de direção
-> logical_target_id continua vazio
-> nenhuma transação de facing de combate
-> MOVE/H continuam bloqueados
```

Telemetria esperada:

```text
PR26_ORIENTATION_HINT ... logical_target=BLOCKED combat_candidate=BLOCKED
PR26_ORIENTATION_HINT_TURN ... logical_target=NONE combat_lock=False facing_transaction=NONE
```

## Invariante do alvo lógico

A estratégia recebe candidatos somente depois desta cadeia completa:

```text
mudança em uma célula
+
corpo bruto/Target Capsule vinculado à mesma mudança
+
HOSTILE_CONFIRMED
+
COMBAT_LOCK
+
PR26_ROUND_TARGET_LATCHED
-> candidato pode entrar no GridFocusStrategy
-> logical_target_id pode existir
```

Sem um latch hostil válido:

```text
combat candidates = ()
logical_target_id = None
state = SEARCH
```

Se qualquer camada antiga tentar criar um alvo lógico antes do latch, a estratégia executa:

```text
PR26_FALSE_LOGICAL_TARGET_RESET
-> reset_round()
-> SEARCH
```

## ReID somente depois do latch

`OCCLUDED_COAST`, `REID_LOCAL`, `CONTACT_MEMORY` e `REID_PENDING` são estados de continuidade de um inimigo já confirmado, não estados de aquisição inicial.

Para existir memória válida, são obrigatórios:

```text
round target memory presente
last_raw_track_id presente
entity_state = ENTITY_CONFIRMED
hostility_state = HOSTILE_CONFIRMED
```

Uma memória sem identidade corporal é removida com:

```text
PR26_INVALID_LATCH_REJECTED reason=NO_SAME_CELL_BODY_ID
```

Sem latch válido, o sistema retorna a `SEARCH` em vez de procurar por 90 segundos um alvo que nunca foi confirmado.

## Geometria raw-less

Mudanças sem corpo bruto podem, no máximo, sugerir orientação quando forem realmente compactas e verticais:

```text
uma única célula
largura 8..48 px
altura 28..78 px
altura >= 1.20 * largura
changed ratio 0.035..0.35
área e blob limitados
```

Componentes como estes têm autoridade zero:

```text
64x64
64x33
célula quase inteira alterada
faixa superior
campo largo
```

Eles não podem criar `ENTITY_CONFIRMED`, `face_only_lock`, orientação ou combate apenas por `motion_votes`.

## Sobreposição com o jogador

A máscara central estreita da PR26.13 permanece ativa. Ela remove somente o núcleo estável do jogador e preserva pixels do inimigo vindos pela esquerda, direita ou por cima.

Fragmentos `WEAK` continuam elegíveis somente quando um corpo bruto ou Target Capsule coincide com a mudança da mesma célula.

## Barreira física final

Sem latch hostil válido:

```text
TURN transaction = bloqueada
MOVE = bloqueado
H = bloqueado
R ofensivo = bloqueado
```

Um `orientation_hint` fresco pode executar somente um pulso isolado de direção, com repetição limitada. Esse pulso não altera a memória lógica de combate.

Depois de um latch legítimo, a continuidade PR26.9 volta a operar normalmente:

```text
visual confirmado -> facing/chase/H
perda visual -> memória/ReID local
ReID pendente -> MOVE/H bloqueados
KO -> memória liberada
```

## JSONs de eventos

Os metadados de `FACE_ONLY_LOCK_CHANGED`, `AIM_UNCONFIRMED`, `R_AUTHORITY_CHANGED` e outros eventos agora são congelados no frame que disparou o evento.

Cada JSON registra:

```text
snapshot_timing = EVENT_TRIGGER_FRAME
occupancy = estado daquele frame
decision = decisão daquele frame
candidate = corpo daquele frame
```

O estado final da rodada não sobrescreve mais o snapshot do evento.

## Validação automática

A suíte cobre especificamente:

- rejeição do salto físico `(-11,+29, response=0.100)`;
- confirmação temporal de uma tradução real de câmera;
- aceitação imediata somente de pequenas correções estáveis;
- componente físico `25x44` elegível apenas como orientação raw-less;
- rejeição de componentes `64x64` e `64x33` como entidades raw-less;
- memória ReID exigindo corpo bruto e hostilidade confirmada;
- todos os contratos determinísticos da PR25;
- parsing dos launchers PowerShell.

No head validado, `182` testes pytest, os `15` cenários determinísticos e os dois launchers PowerShell passaram.

A PR permanece Draft e não deve ser mesclada antes de um novo teste físico no Windows.
