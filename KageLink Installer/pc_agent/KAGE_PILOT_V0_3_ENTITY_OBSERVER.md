# Kage Pilot v0.3 — Entity Observer

## Objetivo

A v0.3 introduz uma camada de percepção explícita antes do aprendizado de combate. O Observer é **somente leitura**: ele captura a janela `Shinobi Story Online`, detecta movimento, mantém entidades temporais e calcula um `Enemy Score`, mas não envia teclas ao jogo.

## Pipeline

```text
captura HWND
    ↓
recorte da arena
    ↓
CLAHE / contraste local
    ↓
Lucas–Kanade (goodFeaturesToTrack + calcOpticalFlowPyrLK)
    ↓
movimento global da câmera
    ↓
compensação do frame anterior
    ↓
diferença temporal + contornos
    ↓
candidatos
    ↓
Entity Tracker
    ↓
memória temporal
    ↓
Enemy Score
    ↓
overlay / JSONL
```

## Conceito de movimento real

O Observer estima o deslocamento mediano da cena com optical flow. Esse valor representa aproximadamente o movimento global provocado pela câmera. Cada entidade é comparada com a posição que teria caso acompanhasse somente esse movimento global.

```text
movimento observado da entidade
- movimento global da câmera
= movimento residual / próprio
```

Isso evita classificar árvores, chão e outros elementos do mapa como entidades móveis apenas porque Leafos se deslocou.

## PLAYER #000

Nesta primeira versão o player é uma âncora normalizada da câmera, não um modelo visual treinado. O padrão é:

- X: `0.50` dentro da arena.
- Y: `0.55` dentro da arena.
- raio de exclusão: `26 px`.

A posição pode ser calibrada por CLI. O objetivo desta fase é primeiro estabilizar inimigos relativos ao player; depois podemos substituir a âncora por reconhecimento visual do próprio Leafos.

## Entity Tracker

Cada candidato persistente recebe um ID:

```text
ENTITY #004
posição
bbox
observações
idade
velocidade residual
direção
deslocamento acumulado
aproximação do player
forma aproximada
memória de hostilidade
Enemy Score
```

Tracks sobrevivem brevemente sem detecção para lidar com animações, oclusões e frames sem contorno suficiente.

## Enemy Score

O score atual é heurístico e interpretável. Ele combina:

- persistência temporal;
- movimento residual real;
- aproximação do player;
- distância do player;
- plausibilidade geométrica do candidato;
- vetor de movimento apontando para o player;
- memória temporal de comportamento hostil.

O padrão para selecionar `TARGET` é `55%`. Esse número deverá ser calibrado com observações reais antes de controlar Leafos.

## Instalação

Depois de atualizar a branch:

```powershell
cd "C:\Users\Rafael\Desktop\Obsidian\LeafOS-Vault\repositories\KageLink\KageLink Installer\pc_agent"
.\.venv-kage-pilot\Scripts\python.exe -m pip install -r requirements.txt
```

## Executar

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_entity_observer.py
```

O Observer abre uma preview redimensionável. Ele não controla o jogo. Jogue manualmente e observe se as caixas acompanham o inimigo.

Para encerrar: `F10`, `Q` ou `ESC` na preview.

## Log para análise

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_entity_observer.py --log entity_observer.jsonl
```

O JSONL registra flow global, posição do player, entidades, velocidade, distância, aproximação e Enemy Score. Esses dados poderão alimentar o controlador e futuros modelos visuais.

## Calibração inicial

Exemplo:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_entity_observer.py --player-x 0.50 --player-y 0.55 --player-radius 26 --enemy-threshold 55
```

Se o círculo `PLAYER #000` não estiver sobre Leafos, ajuste `--player-x` e `--player-y` antes de avaliar o Enemy Score.

## Critério de sucesso desta etapa

Ainda não é vencer uma luta.

A v0.3a está validada quando:

1. `PLAYER #000` está corretamente ancorado.
2. Um inimigo recebe o mesmo `ENTITY #` por vários frames.
3. O track sobrevive a pequenas oclusões/animações.
4. O deslocamento global do mapa não é confundido com movimento próprio.
5. Um inimigo aproximando-se aumenta seu Enemy Score.
6. Após knockback, a distância e a direção relativas ao player mudam de forma coerente.
7. O target correto permanece selecionado durante o combate.

Somente depois disso o Kage Pilot deverá reutilizar `R +REP`, movimento e `H` na camada de controle.
