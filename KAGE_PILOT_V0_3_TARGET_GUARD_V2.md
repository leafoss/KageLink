# Kage Pilot v0.3 — Target Guard v2

## Motivo

A validação real mostrou que o `BACKGROUND_DYNAMIC` já aprende e reduz fortemente os falsos positivos da água, mas algumas entidades ambientais ainda conseguiam acumular `Enemy Score` alto e receber `TARGET LOCK`.

A correção separa explicitamente três conceitos:

```text
movimento -> ENTITY -> TARGET elegível
```

`Enemy Score` continua sendo um diagnóstico. Ele não é mais suficiente sozinho para criar um lock de combate.

## Posição padrão do PLAYER

A posição padrão do `PLAYER #000` foi atualizada para a última calibração validada no combate real:

```text
player-x = 0.5181
player-y = 0.4706
PLAYER box = 18x38 px
```

O clique esquerdo continua disponível para refinamento manual.

## Regras de TARGET

- `LOST`: continua na memória do tracker/reacquisition, mas nunca é TARGET ativo;
- `OCCLUDED`: continua elegível porque representa contato conhecido na borda do PLAYER;
- `VISIBLE` próximo do player: pode ser elegível após persistência mínima;
- `VISIBLE` distante: precisa demonstrar aproximação coerente, velocidade residual e memória temporal;
- região `BACKGROUND_DYNAMIC` madura + entidade distante: bloqueia aquisição de TARGET independentemente do `Enemy Score`;
- entidade muito nova: não pode adquirir TARGET instantaneamente.

Padrões iniciais:

```text
target minimum age          = 0.70 s
target minimum observations = 4
near target distance        = 145 px
far approach maximum        = 280 px
dynamic-region block        = 0.42
```

## Segurança conceitual

A v0.3 continua somente leitura. Nenhuma tecla é enviada ao jogo.

A regra central passa a ser:

```text
MOVIMENTO != ENTITY
ENTITY != INIMIGO
INIMIGO != TARGET
```

O controlador futuro só deverá consumir `TARGET`, nunca candidatos brutos ou qualquer entidade com score alto.
