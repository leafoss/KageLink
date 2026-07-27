# Kage Pilot v0.3 — Fundo Dinâmico por Recorrência Temporal

## Motivo da revisão

O teste real no BYOND mostrou que a água animada podia produzir muitos `ENTITY`, mas o filtro anterior permanecia em `dynamic bg cells: 0` mesmo após mais de 10.000 frames. A causa era exigir densidade local de candidatos no mesmo frame: os contornos da água ficavam espalhados ao longo de uma faixa larga e não necessariamente tinham três vizinhos dentro de 58 px.

## Nova regra

A memória ambiental agora aprende **recorrência temporal por região**.

```text
movimento reaparece na mesma célula
        ↓
acumula hits ao longo do tempo
        ↓
célula amadurece
        ↓
BACKGROUND_DYNAMIC
```

A aparência continua sendo usada como evidência, mas deixou de ser obrigatória para contornos claramente semelhantes a cenário. Candidatos com formato vertical de personagem exigem evidência regional e visual mais forte antes de serem suprimidos.

O tracker de combate continua protegendo candidatos próximos do player, em `OCCLUDED`, ou com trajetória coerente de aproximação.

## Telemetria

O Observer imprime uma linha a cada 2 segundos por padrão:

```text
OBS t=  12.0s entities= 15 bg_mature= 8 bg_strong= 3 suppressed= 6 pruned= 2 dormant= 1 target=#042/VISIBLE/RIGHT/67.0%
```

Campos:

- `entities`: tracks ativos;
- `bg_mature`: células de fundo dinâmico maduras;
- `bg_strong`: células com evidência ambiental forte;
- `suppressed`: candidatos descartados antes de virar track;
- `pruned`: tracks antigos removidos retroativamente como fundo;
- `dormant`: identidades aguardando reacquisition;
- `target`: ID, estado, lado relativo e Enemy Score do alvo atual.

A frequência pode ser alterada com `--telemetry-seconds`. Use `--telemetry-seconds 0` para desativar.

## Recalibração do PLAYER

Clicar novamente sobre Leafos reinicia entidades e TARGET LOCK, mas preserva a memória ambiental já aprendida.

## Gate de validação

Durante um teste parado perto da água, esperamos que `bg_mature` deixe de permanecer em zero, que `suppressed`/`pruned` comecem a crescer e que `entities` caia conforme a região é aprendida. Em combate, o inimigo real deve continuar protegido pela coerência temporal e pela relação espacial com o player.
