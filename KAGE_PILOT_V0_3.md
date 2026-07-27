# Kage Pilot v0.3 — Entity Observer

## Objetivo

A v0.3 abandona temporariamente a tentativa de decidir combate diretamente a partir da imagem inteira. Antes de controlar Leafos, o sistema precisa construir uma representação explícita do mundo:

```text
captura HWND
    ↓
contraste local (CLAHE)
    ↓
contornos e movimento
    ↓
Lucas–Kanade optical flow
    ↓
compensação do movimento global da câmera
    ↓
Entity Tracker
    ↓
memória temporal
    ↓
Enemy Score
```

Esta primeira etapa é **somente observação**. Nenhuma tecla é enviada ao jogo.

## O que aparece na janela

- `PLAYER #000`: âncora inicial do jogador, calibrável por posição normalizada.
- `ENTITY #NNN`: candidatos persistentes encontrados por movimento e contornos.
- trilha temporal de cada entidade;
- velocidade residual após compensar o movimento global da cena;
- direção;
- tempo observado;
- aproximação em relação ao player;
- distância ao player;
- memória de hostilidade;
- `ENEMY SCORE` de 0% a 100%;
- máscara de movimento usada para gerar candidatos.

## Enemy Score inicial

O score ainda é heurístico. Ele combina:

- persistência temporal;
- movimento independente do cenário;
- aproximação do player;
- direção do movimento em relação ao player;
- distância plausível;
- formato/tamanho do candidato;
- memória acumulada de comportamento hostil.

Esse score não é uma verdade final. Ele existe para tornar as decisões visíveis e calibráveis antes de introduzir um modelo visual treinado.

## Instalação

Na pasta `KageLink Installer/pc_agent`:

```powershell
.\.venv-kage-pilot\Scripts\python.exe -m pip install -r requirements.txt
```

A v0.3 adiciona OpenCV e NumPy ao ambiente do PC Agent.

## Executar

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py
```

Teclas da janela de observação:

```text
Q ou ESC = sair
```

O Observer não envia essas teclas ao Shinobi Story Online; elas são lidas apenas pela janela de preview do OpenCV.

## Calibração inicial do player

A primeira versão usa uma âncora relativa da câmera para o player. Os parâmetros padrão são:

```text
player-x = 0.50
player-y = 0.55
player-radius = 26
```

Exemplo:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py `
  --player-x 0.48 `
  --player-y 0.58 `
  --player-radius 30
```

O círculo `PLAYER #000` deve cobrir Leafos sem englobar o inimigo. Essa exclusão impede que o próprio jogador seja criado como entidade hostil.

## Critério de validação

A v0.3a será considerada validada quando, durante uma luta real:

1. o mesmo inimigo mantiver o mesmo `ENTITY ID` por vários segundos;
2. o tracker não interpretar o cenário inteiro como inimigos quando a câmera se mover;
3. `approaches player` mudar para `SIM` quando o inimigo avançar;
4. a distância ao player aumentar depois de um empurrão;
5. o `Enemy Score` do inimigo real superar objetos e efeitos temporários;
6. a caixa e a trilha continuarem acompanhando o alvo.

## Próxima etapa

Somente após validar o Observer será criado o controlador v0.3b:

```text
SEARCH → APPROACH → MELEE → DISPLACED → RECOVER → POST_COMBAT
```

A decisão de `LEFT`, `RIGHT`, `R +REP` e `H` será baseada no estado espacial do alvo, não em semelhança global entre frames.
