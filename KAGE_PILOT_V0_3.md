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

- `PLAYER #000`: âncora inicial do jogador, calibrável por posição normalizada ou clique direto na janela.
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

Controles da janela de observação:

```text
clique esquerdo em Leafos = recalibrar PLAYER #000
Q ou ESC = sair
```

O Observer não envia essas ações ao Shinobi Story Online; elas são lidas apenas pela janela de preview do OpenCV.

## Calibração inicial do player

A primeira validação real mostrou que a âncora antiga `0.50 / 0.55` ficava abaixo de Leafos e permitia que o próprio player fosse criado como `ENTITY`. O padrão foi recalibrado para aproximadamente:

```text
player-x = 0.51
player-y = 0.48
player-radius = 26
```

A calibração recomendada agora é visual:

1. execute o Observer;
2. clique com o botão esquerdo exatamente sobre Leafos;
3. o `PLAYER #000` é movido imediatamente;
4. o tracker é zerado para remover qualquer falsa entidade criada com a âncora antiga;
5. o PowerShell imprime os valores `--player-x` e `--player-y` correspondentes ao clique.

Exemplo de reaproveitamento manual:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py `
  --player-x 0.5100 `
  --player-y 0.4800 `
  --player-radius 26
```

O círculo `PLAYER #000` é uma zona de exclusão, não precisa reproduzir exatamente o contorno do sprite. Ele deve cobrir Leafos sem bloquear excessivamente a área ao redor. Entidades já rastreadas podem entrar nessa zona durante melee sem perder o `ENTITY ID`.

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
