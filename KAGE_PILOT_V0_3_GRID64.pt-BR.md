# Kage Pilot v0.3 — GRID 64 px e Contact Memory confirmado

## Evidência real

Os testes no Shinobi Story Online mostraram que a GRID de 32 px atravessava visualmente a cabeça/corpo dos personagens. Imagens de referência com dois personagens em células verticais adjacentes indicam que um personagem ocupa aproximadamente uma faixa de 64 px.

A hipótese operacional da v0.3 passa a ser:

```text
célula visual/lógica = 64 x 64 px
```

Ela continua configurável via `--grid-size`.

## Alinhamento automático

A origem da GRID não é mais simplesmente `(0,0)` do frame. Por padrão, o Observer calcula o deslocamento da malha para que `PLAYER #000` fique no centro de uma célula de 64 px.

Ao recalibrar o PLAYER com clique esquerdo, a GRID é realinhada no próximo frame sem apagar a memória ambiental já aprendida.

Para diagnóstico manual continuam disponíveis:

```text
--grid-origin-x
--grid-origin-y
```

Os dois devem ser fornecidos juntos.

## CONTACT MEMORY confirmado

Um falso contorno próximo ao PLAYER não deve abrir imediatamente uma memória de combate.

A regra padrão agora exige 2 frames coerentes no mesmo lado/célula adjacente antes de um novo contato poder abrir o `CONTACT MEMORY`.

Um TARGET já validado pode continuar sendo mantido durante degradação visual de melee, e `CONTACT_REBIND` ainda pode reassociar um novo contorno próximo enquanto a janela de contato estiver válida.

## Arquitetura híbrida

```text
OpenCV / contornos
        +
Lucas-Kanade
        +
Entity Tracker
        +
Background Dynamic
        +
GRID 64x64 alinhada
        +
Contact Memory confirmado
        ↓
TARGET lógico
```

O Observer permanece somente leitura e não envia nenhuma tecla ao jogo.
