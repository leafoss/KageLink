# PR26.9 — Latched hostile target continuity

A PR26 permanece empilhada sobre a PR25 e mantém a grade imutável de 64 px, os contratos de movimento, facing, R, pulso H de 50 ms, cooldown de 5 s, F12, KO autoritativo por chat e recuperação pós-combate.

## Falha física corrigida

O log da PR26.8 comprovou que o inimigo era detectado, selecionado, orientado para `UP`, confirmado por `COMBAT_LOCK` e atacado. No frame imediatamente seguinte, a ausência temporária do cluster fazia o sistema entrar em `OCCLUDED_COAST`, `REID_LOCAL` e depois abandonar a identidade. A mesma entidade reaparecia mais tarde e recebia um novo ID.

A causa era arquitetural: o lock visual era tratado como a própria identidade. Animação, sobreposição com o jogador, movimento de câmera ou um frame sem componente destruíam a autoridade, apesar de Target Capsule, aparência, posição e histórico já conhecerem o alvo.

## Contrato da PR26.9

```text
primeiro HOSTILE_CONFIRMED -> COMBAT_LOCK
-> latch de uma identidade de inimigo da rodada
-> identidade permanece até KO/fim da rodada
```

Um candidato com score maior não substitui o alvo latched durante contato, animação ou oclusão.

## ReID progressivo local

```text
0–2.5 s  -> procurar em D1
2.5–7 s  -> procurar em D2
>7 s     -> procurar em D3
nunca procurar além de D3
```

A reacquisição utiliza, nesta ordem:

1. Target Capsule aplicada aos candidatos crus antes do filtro de ocupação;
2. componente local compacto sobre baseline exata;
3. geometria prevista compensada pela câmera.

## Sobreposição em contato

A aquisição inicial mantém a máscara maior do jogador. Depois que o inimigo é confirmado, a exclusão passa a usar somente um núcleo de `22x42 px`, evitando que a máscara do jogador apague também o sprite hostil quando os dois se encostam.

## Autoridade física

```text
VISUAL_CLUSTER / CAPSULE_REID / PIXEL_REID
-> alvo visual atual
-> chase/H permitidos conforme PR25

CONTACT_MEMORY / REID_PENDING / OUTSIDE_D3
-> identidade e facing anterior preservados
-> MOVE bloqueado
-> H bloqueado
-> troca de alvo bloqueada
```

Não existe perseguição ou ataque cego durante memória ou ReID.

## Associação protegida

A identidade latched rejeita associações que:

- deixem de ter geometria corporal compacta;
- saltem mais de 176 px da previsão compensada;
- apareçam além de D3;
- tentem transformar campo largo, faixa de UI ou cenário em continuação do alvo.

## Telemetria principal

```text
PR26_ROUND_TARGET_LATCHED
PR26_TARGET_MEMORY
PR26_TARGET_REID_CONFIRMED source=TARGET_CAPSULE
PR26_TARGET_REID_CONFIRMED source=LOCAL_PIXEL_CLUSTER
PR26_TARGET_ASSOCIATION_REJECTED
PR26_TARGET_OUTSIDE_D3
```

## Validação

A última execução automática registrou:

- 163 testes pytest aprovados;
- 15 cenários determinísticos da PR25 aprovados;
- dois launchers PowerShell analisados com sucesso;
- GitHub Actions verde.

A PR permanece Draft e não deve ser mesclada antes do teste físico.
