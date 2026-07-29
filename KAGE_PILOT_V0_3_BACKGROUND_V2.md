# Kage Pilot v0.3 — Background Dynamic v2

## Por que a primeira versão falhou na água

O primeiro filtro de fundo dinâmico dependia fortemente de duas condições simultâneas:

- vários candidatos próximos;
- alta similaridade visual entre o candidato atual e a memória da região.

Na água animada do Shinobi Story Online os contornos mudam de formato e posição continuamente. A mesma faixa de água podia, portanto, gerar dezenas de `ENTITY #NNN` mesmo sendo claramente cenário.

## Nova estratégia: ocupação temporal

A v2 aprende onde movimento denso retorna repetidamente:

```text
movimento detectado
    ↓
vários candidatos próximos
    ↓
bounding boxes ocupam as mesmas células da arena
    ↓
atividade persiste por vários frames
    ↓
BACKGROUND_DYNAMIC
```

A aparência continua sendo usada, mas como evidência auxiliar. Regiões com ocupação forte e repetitiva podem ser suprimidas mesmo quando a animação muda visualmente.

## Proteção de entidades reais

O filtro não deve apagar um inimigo apenas porque ele atravessou uma região com água animada.

Tracks já estabelecidos são protegidos quando apresentam sinais de combate, por exemplo:

- proximidade do player;
- aproximação do player;
- memória de hostilidade;
- estado `OCCLUDED` durante contato.

## Limpeza retroativa

A primeira versão filtrava novos candidatos, mas uma entidade falsa criada antes de a água ser aprendida podia continuar viva pelo TTL e até competir por `TARGET LOCK`.

A v2 também revisa tracks ativos. Um track distante do player, sem comportamento hostil, dentro de uma região fortemente dinâmica e com movimento pouco coerente pode ser removido como fundo animado.

Isso permite que o contador `entities` caia depois que a região é aprendida, em vez de apenas impedir novos falsos positivos.

## Recalibração do PLAYER

A calibração por clique continua limpando entidades e lock, mas não apaga mais a memória ambiental já aprendida.

Isso é importante porque vários cliques de ajuste sobre Leafos não devem fazer o Observer esquecer a água e iniciar o aprendizado do zero.

## Validação esperada

Ao aproximar Leafos de uma faixa de água animada:

1. inicialmente alguns candidatos podem aparecer;
2. `dynamic bg cells` deve crescer;
3. `dynamic bg suppressed` deve começar a aumentar;
4. o número de `entities` deve cair significativamente;
5. a água não deve adquirir ou manter `TARGET LOCK`;
6. um inimigo real próximo do player deve continuar rastreável mesmo na presença da animação.

Esta camada continua **somente observação** e não envia nenhuma tecla ao jogo.
