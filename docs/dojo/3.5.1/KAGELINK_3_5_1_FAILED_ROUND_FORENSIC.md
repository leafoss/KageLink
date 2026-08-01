# KageLink 3.5.1 — análise forense da primeira derrota física

## Status

Esta análise registra uma **regressão física grave** observada no vídeo:

```text
round_001_20260731_184428_19600.avi
```

O vídeo possui 106 quadros diagnósticos, 2 fps, resolução 1280×720 e aproximadamente 53 segundos.

A existência de testes automatizados aprovados antes desta captura não significava que o comportamento estivesse fisicamente correto. A rodada foi perdida e a correção anterior não pode ser considerada aprovada.

## Correção importante sobre o grid

A primeira inspeção visual sugeriu aproximadamente 72 pixels por célula. A medição do frame bruto e a revisão do runtime corrigiram essa interpretação:

```text
modo lógico: 64
cell_size efetivo: 64 px
PNG do Trainer: 72×73 px
```

O PNG 72×73 participa somente do matching visual do Trainer. Ele não define o grid de navegação.

O defeito real do grid era o **ponto de ancoragem**:

```text
antes: centro visual do sprite
correto: célula sob os pés do personagem
```

Como o centro do sprite pode ficar aproximadamente meia célula acima do piso ocupado, PLAYER e TARGET eram colocados na linha errada, causando falsos `d=0`, `d=1`, direção incorreta e parada/movimento no momento errado.

## Linha do tempo observada

### 0–4 segundos

- Uma identidade lógica foi criada antes de existir um corpo inimigo confiável.
- O estado entrou em `OCCLUDED_PREDICTED` com pouquíssima evidência visual.
- Um contorno vertical grande próximo ao jogador passou a representar contato.

### 6–16 segundos

- A mesma identidade lógica começou a trocar rapidamente de visual track.
- Foram observados tracks `#2`, `#7` e outros associados ao mesmo combate.
- Efeitos horizontais e verticais de ataque permaneceram elegíveis.
- A direção registrada e o comando executado chegaram a divergir, incluindo combinações equivalentes a direção LEFT com `FACE:right` e direção DOWN com `FACE:up`.

### 18–30 segundos

- Grandes regiões da máscara de movimento, faixas horizontais e efeitos próximos ao jogador continuaram gerando tracks.
- A confiança permaneceu próxima de 1,0 mesmo quando a identidade visual mudava.
- Em aproximadamente 30 segundos, o alvo registrado estava `LOST/OCCLUDED_PREDICTED`, enquanto a memória previa uma posição à direita do jogador e o contato físico relevante não correspondia àquela previsão.
- O modo ainda podia permanecer em `PURSUIT`.

### 32–50 segundos

- A identidade lógica continuou saltando entre tracks como `#3`, `#5`, `#21` e `#40`.
- O alvo lógico envelheceu por mais de 70 segundos, apesar de sucessivas substituições visuais.
- A memória de direção antiga continuou influenciando comandos.
- O personagem ultrapassou a região útil de contato e não reconstruiu corretamente a relação física com o adversário.

## Causas-raiz

### 1. Centro do sprite usado como geometria

Distância e direção eram calculadas com `player_center` e `track.center`. Isso mistura desenho do sprite com a célula física ocupada.

### 2. Proximidade concedia autoridade indevida

A correção anterior priorizava qualquer track próximo em `d<=2`, inclusive `OCCLUDED`, sem exigir forma corporal confiável. Um efeito perto do jogador podia substituir o alvo real.

### 3. Memória visual permissiva demais

O rebind aceitava `VISIBLE` ou `OCCLUDED`, limiar baixo, uma única observação e timeout de até 8 segundos. Isso preservava uma identidade lógica mesmo após várias trocas físicas incompatíveis.

### 4. Direção antiga podia substituir a medição atual

A camada persistente podia sobrescrever a direção do frame atual com `last_contact_direction`, produzindo divergência entre `DIRECTION` e `CURRENT COMMAND`.

### 5. Perseguição sem corpo visível

Durante uma ausência curta do target, a memória podia emitir `MOVE_<direção anterior>`. Essa perseguição cega explica o personagem continuar andando depois de ultrapassar o alvo.

### 6. Filtro de efeitos insuficiente na região do jogador

A proximidade ao jogador protegia alguns contornos grandes contra rejeição. Ataques horizontais, colunas verticais, sombras e regiões de borda podiam sobreviver justamente no ponto mais crítico do combate.

## Nova fronteira de autoridade

O pipeline passa a separar observação, identidade e controle:

```text
contorno observado
→ pode continuar aparecendo como diagnóstico
→ só vira corpo autoritativo se estiver VISIBLE e passar pelo body gate
→ identidade pode ser lembrada durante oclusão
→ memória nunca autoriza translação
→ movimento exige corpo VISIBLE atual + geometria atual + direção coerente
```

## Correções implementadas

### Grid físico

- PLAYER e TARGET são ancorados pelos pés.
- Histórico de trajetória também é convertido para âncora dos pés.
- O grid 64 continua com 64 px independentemente do PNG 72×73.
- O overlay passa a mostrar `PLAYER FEET`, `TARGET FEET`, origem, tamanho da célula e células calculadas.

### Body gate

Somente um track `VISIBLE` pode adquirir ou rebindar identidade. São rejeitados:

- contornos muito pequenos;
- contornos largos ou altos demais;
- efeitos horizontais e verticais;
- áreas excessivas;
- shape score fraco;
- novas aquisições em `d=0`;
- sobreposição excessiva com o corpo do jogador;
- grandes regiões de borda.

### Memória conservadora

- `OCCLUDED` não adquire nem rebinda identidade.
- Rebind exige duas observações visíveis consecutivas.
- Limiar mínimo elevado para 0,62.
- Janela total reduzida para no máximo 3 segundos.
- Previsão limitada a 0,35 s em melee e 0,60 s em pursuit.
- Troca de ID visual zera velocidade artificial.

### Movimento fail-closed

- Ausência ou oclusão do corpo resulta em `HOLD` com R mantido.
- Nenhum `MOVE` é autorizado por posição prevista.
- Melee nunca autoriza translação.
- Pursuit exige corpo `VISIBLE`, visto há no máximo 0,20 s e distância `d>=3`.
- Cada pulso de movimento exige nova observação e há intervalo mínimo de 0,75 s.
- Comando e direção precisam apontar para a mesma tecla física.
- Divergências geram bloqueio e telemetria, não movimento.

## Telemetria adicionada

```text
DOJO_COMBAT_BODY_REJECTED
DOJO_COMBAT_MOVE_BLOCKED
DOJO_COMBAT_FACE_BLOCKED
```

O vídeo diagnóstico também passa a exibir:

```text
GRID / GRADE cell=<px> origin=<x,y> anchor=FEET
CELLS / CELULAS PLAYER=<cell> TARGET=<cell> d=<distance>
BODY GATE / CORPO accepted|rejected
PLAYER FEET
TARGET FEET
```

## Gate físico obrigatório

A correção só poderá ser considerada aprovada após um novo teste real confirmar simultaneamente:

1. grid de 64 px alinhado aos pés;
2. efeitos grandes permanecem apenas como tracks diagnósticos e nunca como alvo autoritativo;
3. nenhum alvo é adquirido em `OCCLUDED` ou `LOST`;
4. direção exibida corresponde ao pulso físico;
5. ausência visual mantém R e bloqueia movimento;
6. cada movimento é um único pulso seguido de reobservação;
7. o personagem não ultrapassa o inimigo por perseguição baseada em memória;
8. a luta termina por KO real sem perda da rodada.

A CI verifica integridade de código e empacotamento. Ela não substitui esse gate físico.

A PR #23 permanece aberta, em Draft e sem merge.
