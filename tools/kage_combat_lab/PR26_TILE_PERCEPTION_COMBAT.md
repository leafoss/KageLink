# PR26.15 — Autoridade visual do corpo atual

A PR26 permanece empilhada sobre a PR25 e mantém a grade imutável de `64x64`, comparação individual por célula, Target Capsule, replay integral, diagnóstico de falhas, facing, R, pulso H, F12, KO por chat e recuperação pós-combate.

## Falha física corrigida

O replay da PR26.14 mostrou que o alvo hostil inicialmente latched migrou para uma mudança de terreno:

```text
inimigo real observado
-> alvo latched criado
-> detector perdeu o corpo atual
-> associação genérica conectou o mesmo track lógico a um componente de terreno
-> componentes 43x64 e 64x23 passaram a representar o alvo
-> memória histórica ainda continha last_raw_track_id
-> combat_lock foi reativado sobre parede/piso
-> personagem perseguiu o tile e ignorou o inimigo
```

O JSON final confirmou o estado contraditório:

```text
combat_lock = true
hostility_state = HOSTILE_CONFIRMED
cluster_cells = [(4,1)]
changed_ratio = 0.6599
largest_blob = 2703
hostility_reason = cluster persistent but lacks motion/raw body evidence
```

Um componente sem corpo atual não pode mais atualizar a geometria visual do alvo.

## Contrato da célula de 64 px

Cada célula continua sendo a unidade de comparação:

```text
baseline própria
imagem atual própria
máscara de diferença própria
changed ratio próprio
componente próprio
bbox próprio
```

A célula indica **onde procurar**. Ela não prova que dois objetos dentro dela são a mesma identidade.

## Associação corpo ↔ componente

A igualdade da célula deixou de ser suficiente.

Antes:

```text
candidate.anchor_cell == changed_cell
-> associação aceita
```

Agora:

```text
bbox do corpo sobrepõe o componente
OU
pé do corpo toca pixels alterados do componente
OU
sobreposição geométrica mínima comprovada
-> associação aceita
```

Sem sobreposição real, o corpo e a mudança permanecem entidades diferentes.

## Corpo atual obrigatório

Depois do latch, a identidade lógica pode sobreviver a oclusão, mas a posição visual só pode ser atualizada por:

```text
raw body associado ao componente no frame atual
OU
Target Capsule ReID confirmado
```

Um componente sem `raw_track_ids` não pode ser associado ao track latched. A identidade entra em `CONTACT_MEMORY` e MOVE/H ficam bloqueados até o corpo reaparecer.

Telemetria:

```text
PR26_LATCHED_TERRAIN_REJECTED
PR26_CURRENT_BODY_GATE_BLOCKED
```

## Cluster e pixel ReID

Clusters continuam sendo somente dicas de busca.

```text
cluster -> células para procurar
cluster -> sem identidade
cluster -> sem hostilidade
cluster -> sem direção de combate
cluster -> sem ReID de combate
```

O antigo `LOCAL_PIXEL_CLUSTER` não pode mais restaurar o inimigo latched. ReID ofensivo requer Target Capsule/corpo atual.

## Rejeição de terreno dominante

Os formatos observados no replay físico agora são rejeitados:

```text
43x64 com changed ratio alto e blob grande
64x23 horizontal
célula dominante/quase inteira alterada
```

Esses componentes são classificados como campo de terreno, parede, piso ou transição de câmera, nunca como corpo humanoide.

## Fluxo válido

```text
mudança individual na célula
+
corpo sobreposto aos pixels dessa mudança
+
HOSTILE_CONFIRMED
+
COMBAT_LOCK
+
ROUND_TARGET_LATCHED
-> facing/chase/H
```

Durante perda visual:

```text
identidade lógica preservada
posição anterior preservada
terreno não atualiza a memória
Target Capsule procura em D1 -> D2 -> D3
MOVE/H bloqueados até confirmação
```

## Validação automática

A suíte cobre:

- candidato na mesma célula, mas distante do componente, sendo rejeitado;
- corpo realmente sobreposto aos pixels alterados sendo aceito;
- componente físico `43x64`, ratio `0.6599`, blob `2703`, sendo terreno;
- componente `64x23` sendo terreno horizontal;
- alvo latched exigindo corpo bruto atual;
- todos os contratos determinísticos da PR25;
- parsing dos launchers PowerShell.

No head validado, `187` testes pytest, os `15` cenários determinísticos e os dois launchers PowerShell passaram.

A PR permanece Draft e não deve ser mesclada antes de um novo teste físico no Windows.
