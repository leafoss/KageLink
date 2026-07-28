# Kage Pilot v0.3d — Busca concêntrica do treinador

A v0.3d preserva integralmente a política de combate validada da v0.3c e altera somente a busca pós-combate usada quando não há uma âncora confiável do treinador do Dojo.

## Estratégia

A busca parte da célula em que o pós-combate começou e percorre anéis concêntricos:

```text
raio 1 completo
→ raio 2 completo
→ raio 3 completo
→ ...
```

Em uma grade ortogonal, cada “círculo” é representado por um anel quadrado de distância de Chebyshev. Cada direção continua sendo enviada somente como pulso curto; nenhuma seta fica segurada.

## Arena inicial

A calibração inicial usa uma arena conhecida de 30 células de largura por 24 de altura. Como a posição inicial pode ser qualquer célula, o limite conservador de raio é 29 células.

Esse tamanho é apenas um limite inicial de segurança. A evolução esperada é detectar limites, obstáculos e áreas já visitadas visualmente, removendo a dependência de dimensões fornecidas manualmente.

## Ordem de prioridade

1. usar a âncora persistente do treinador atualizada pelo movimento global da câmera;
2. se não houver âncora, executar busca concêntrica por células;
3. interromper a busca assim que o treinador for reconhecido visualmente;
4. usar a memória apenas para navegação;
5. exigir confirmação visual e adjacência antes de apertar `V`.

## Segurança

- `R` e `H` permanecem desligados no pós-combate;
- setas são apenas pulsos curtos;
- `V` continua sendo toggle: um toque entra e outro sai;
- `F12` solta todas as teclas e encerra imediatamente;
- a v0.3c permanece disponível como versão validada de fallback.
