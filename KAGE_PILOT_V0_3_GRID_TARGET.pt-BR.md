# Kage Pilot v0.3 — GRID Target híbrido

## Objetivo

A validação real mostrou dois comportamentos diferentes:

- o tracker por contornos + Lucas–Kanade funciona bem no combate e consegue preservar IDs durante contato;
- água animada ainda consegue gerar entidades e Enemy Scores altos.

A GRID não substitui o tracker anterior. Ela adiciona uma segunda fonte de evidência espacial.

```text
contornos + Lucas–Kanade + aparência + memória temporal
                         +
                 GRID fixa 32x32
                         ↓
            deslocamento entre células
                         ↓
           aproxima realmente PLAYER?
                         ↓
                 TARGET elegível
```

## GRID

O tamanho de trabalho inicial é `32x32 px`, configurável por `--grid-size`.

A malha é alinhada à origem do frame capturado, e não ao canto do recorte da arena. Isso evita deslocar as células quando o crop começa alguns pixels dentro da janela.

## Evidência de aproximação

Para cada ENTITY, os centros recentes são convertidos em células. Movimentos consecutivos dentro da mesma célula são condensados.

São calculados:

- célula atual;
- distância Chebyshev até a célula do PLAYER;
- quantidade de células únicas visitadas;
- passos que reduziram distância;
- passos que aumentaram distância;
- redução líquida de distância;
- proporção de passos em direção ao PLAYER;
- força de BACKGROUND_DYNAMIC da região.

Uma trajetória distante só é considerada aproximação coerente quando atravessa pelo menos três células, possui ao menos dois passos de aproximação, redução líquida positiva e predominância de movimento em direção ao PLAYER.

## Regra de TARGET

- `OCCLUDED`: elegível, pois contato já foi comprovado.
- célula imediatamente adjacente ao PLAYER: pode ser elegível após a persistência normal do tracker.
- distância de duas ou mais células: exige trajetória coerente pela GRID.
- região de fundo animado forte: continua bloqueada, a menos que exista uma trajetória coerente real até o PLAYER.
- `Enemy Score` sozinho não cria TARGET.

Isso foi feito especificamente para impedir água animada de obter lock por picos de movimento.

## CONTACT MEMORY

Quando um alvo validado chega à célula do PLAYER ou entra em `OCCLUDED`, é criada uma janela curta de memória de contato, inicialmente `2.8 s`.

Durante essa janela:

- o contorno pode desaparecer;
- o ID visual pode oscilar;
- o lock lógico pode continuar como `CONTACT_MEMORY`;
- um novo candidato que reapareça colado ao PLAYER no mesmo lado pode reassociar o lock como `CONTACT_REBIND`.

Um track `LOST` nunca renova sua própria janela de contato. Somente `VISIBLE` adjacente ou `OCCLUDED` podem estendê-la.

## Overlay e telemetria

A GRID aparece sobre a arena por padrão. Pode ser ocultada com:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py --no-grid-overlay
```

A telemetria agora inclui:

```text
grid_active=N
target=#NNN/STATE/SIDE/SCORE
grid[cell=x,y d=N toward=N away=N net=N bg=0.xx]
```

O parâmetro `d` é a distância em células até o PLAYER.

## Critério de validação

Água:

```text
TARGET deve permanecer none
```

mesmo que existam ENTITYs e Enemy Scores altos.

Combate:

```text
ENTITY distante
  ↓
travessa células em direção ao PLAYER
  ↓
TARGET
  ↓
adjacente / OCCLUDED
  ↓
CONTACT MEMORY
  ↓
reaparece
  ↓
mesmo lock lógico / CONTACT REBIND
```

Esta revisão continua somente observação e não envia teclas ao jogo.
