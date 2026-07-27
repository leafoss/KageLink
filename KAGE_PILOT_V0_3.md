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
    ↓
TARGET LOCK
```

Esta primeira etapa é **somente observação**. Nenhuma tecla é enviada ao jogo.

## O que aparece na janela

- `PLAYER #000`: âncora calibrável do jogador;
- caixa vertical apertada do player, em vez do antigo círculo de exclusão;
- `ENTITY #NNN`: candidatos persistentes encontrados por movimento e contornos;
- trilha temporal de cada entidade;
- velocidade residual após compensar o movimento global da cena;
- direção;
- tempo observado;
- aproximação em relação ao player;
- distância ao player;
- memória de hostilidade;
- `ENEMY SCORE` de 0% a 100%;
- estado de `TARGET LOCK`;
- máscara de movimento usada para criar candidatos.

## Caixa do PLAYER

O círculo inicial foi substituído por um retângulo vertical, mais próximo do volume ocupado pelo sprite real e com menos área vazia protegida.

Padrão atual:

```text
player-box-width  = 18 px
player-box-height = 38 px
```

A caixa é uma **zona de exclusão para criação de novas entidades**. Ela impede que o próprio Leafos seja criado como `ENTITY`, mas não apaga uma entidade já conhecida quando um inimigo entra em melee ou sobrepõe o player.

A posição pode ser calibrada clicando com o botão esquerdo exatamente sobre Leafos na janela do Observer. A calibração reinicia a memória temporal para remover falsos tracks criados pela posição anterior.

## Entity Tracker estável

O tracker v0.3 agora usa quatro sinais para preservar identidade:

1. movimento global da câmera estimado por Lucas–Kanade;
2. velocidade residual recente da própria entidade;
3. distância até a posição prevista;
4. consistência de tamanho/formato da bounding box.

A posição esperada de uma entidade considera tanto o movimento da câmera quanto sua velocidade residual recente. Isso ajuda a recuperar o mesmo ID quando um contorno some por poucos frames ou quando o alvo sofre um deslocamento rápido.

Parâmetros padrão de teste real:

```text
track-match-distance = 105 px
track-ttl            = 2.0 s
```

Durante pequenos drop-outs, parte da velocidade anterior é preservada e decai gradualmente em vez de ser zerada imediatamente.

## TARGET LOCK com hysteresis

Adquirir um alvo e manter um alvo são operações diferentes.

Padrões:

```text
target-acquire = 55%
target-keep    = 38%
```

Fluxo:

```text
sem alvo
  ↓
ENTITY >= 55%
  ↓
TARGET LOCK
  ↓
score pode oscilar entre 38% e 55%
  ↓
continua TARGET
  ↓
score < 38% ou entidade expira
  ↓
solta o lock
```

Isso evita trocar/perder o alvo por pequenas oscilações de um único frame.

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

A v0.3 usa OpenCV e NumPy no ambiente do PC Agent.

## Executar

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py
```

Parâmetros opcionais:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py `
  --player-box-width 18 `
  --player-box-height 38 `
  --match-distance 105 `
  --track-ttl 2.0 `
  --target-acquire 55 `
  --target-keep 38
```

Controles da janela de observação:

```text
clique esquerdo em Leafos = recalibrar PLAYER
Q ou ESC                  = sair
```

O Observer não envia essas ações ao Shinobi Story Online; elas são lidas apenas pela janela de preview do OpenCV.

## Critério de validação

A v0.3a será considerada validada quando, durante uma luta real:

1. `PLAYER #000` cobrir o sprite com uma caixa vertical apertada;
2. o próprio player não nascer como `ENTITY`;
3. o mesmo inimigo mantiver o mesmo `ENTITY ID` por vários segundos;
4. o tracker não interpretar o cenário inteiro como inimigos quando a câmera se mover;
5. `approaches player` mudar para `SIM` quando o inimigo avançar;
6. a distância ao player aumentar depois de um empurrão;
7. o `Enemy Score` do inimigo real superar objetos e efeitos temporários;
8. depois de adquirido, o `TARGET LOCK` sobreviver a pequenas oscilações de score;
9. a caixa e a trilha continuarem acompanhando o alvo.

## Próxima etapa

Somente após validar o Observer será criado o controlador v0.3b:

```text
SEARCH → APPROACH → MELEE → DISPLACED → RECOVER → POST_COMBAT
```

A decisão de `LEFT`, `RIGHT`, `R +REP` e `H` será baseada no estado espacial do alvo, não em semelhança global entre frames.
