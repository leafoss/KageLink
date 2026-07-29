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
BACKGROUND_DYNAMIC memory
    ↓
Entity Tracker + aparência
    ↓
memória temporal / oclusão / lado relativo
    ↓
Enemy Score
    ↓
TARGET LOCK
```

Esta etapa continua **somente observação**. Nenhuma tecla é enviada ao jogo.

## O que aparece na janela

- `PLAYER #000`: âncora calibrável do jogador;
- caixa vertical apertada do player;
- `ENTITY #NNN`: candidatos persistentes;
- trilha temporal;
- velocidade residual após compensação da câmera;
- direção e lado relativo (`LEFT/RIGHT/UP/DOWN`);
- estado `VISIBLE`, `LOST` ou `OCCLUDED`;
- similaridade visual usada para associação;
- tempo observado, distância e aproximação;
- memória de hostilidade e `ENEMY SCORE`;
- `TARGET LOCK`;
- contagem de candidatos descartados por `BACKGROUND_DYNAMIC`;
- identidades dormentes aguardando reacquisition.

## Caixa do PLAYER

O antigo círculo foi substituído por um retângulo vertical mais próximo do volume real do sprite.

```text
player-box-width  = 18 px
player-box-height = 38 px
```

A caixa impede a criação de uma nova entidade em cima do próprio Leafos. Uma entidade já conhecida pode chegar até o player, mas sua caixa lógica não atravessa o núcleo do `PLAYER #000`.

A posição continua calibrável com clique esquerdo diretamente sobre Leafos. A recalibração reinicia tracker e TARGET LOCK, mas preserva a memória ambiental já aprendida.

## BACKGROUND_DYNAMIC

A água e outros elementos animados podem gerar muitos contornos apesar de não serem entidades. A validação real mostrou que a água pode produzir contornos espalhados por uma faixa larga; por isso o filtro atual não exige mais que três candidatos estejam próximos no mesmo frame.

A memória ambiental usa **recorrência temporal por região**:

```text
movimento reaparece na mesma célula
        ↓
acumula hits ao longo do tempo
        ↓
célula amadurece
        ↓
BACKGROUND_DYNAMIC
```

A aparência continua como evidência de apoio, mas deixou de ser obrigatória para contornos claramente parecidos com cenário. Candidatos verticais com formato de personagem exigem evidência regional e visual mais forte antes de serem suprimidos.

Padrões iniciais:

```text
background cell size       = 32 px
minimum frame activity     = 3 candidatos remotos
minimum temporal hits      = 8
minimum age                = 0.8 s
appearance similarity      = 0.88
memory TTL                 = 12 s
```

O painel mostra:

```text
dynamic bg suppressed: N
dynamic bg cells: N
```

O tracker de combate protege candidatos próximos ao player, em `OCCLUDED` ou com trajetória coerente de aproximação. Tracks antigos dentro de uma região fortemente dinâmica também podem ser removidos retroativamente como `BACKGROUND_DYNAMIC`.

## Memória de aparência

Cada candidato recebe uma assinatura visual leve construída a partir de:

- histograma de intensidade;
- estrutura grosseira em quadrantes;
- densidade de bordas.

Não é um modelo neural. É uma memória visual barata usada para:

- reduzir troca de IDs entre candidatos próximos;
- reconhecer padrões ambientais semelhantes;
- ajudar a recuperar o mesmo `ENTITY ID` depois de uma perda visual.

A aparência entra junto com posição prevista, tamanho e formato no custo de matching.

## Entity Tracker estável

O tracker usa:

1. movimento global da câmera por Lucas–Kanade;
2. velocidade residual da entidade;
3. posição prevista;
4. tamanho/formato da bounding box;
5. similaridade de aparência;
6. lado relativo ao player.

Parâmetros principais:

```text
track-match-distance = 105 px
track-ttl            = 2.0 s
```

Durante drop-outs curtos, a velocidade decai gradualmente em vez de zerar instantaneamente.

## OCCLUDED / contato com PLAYER

Quando a bounding box observada tenta atravessar a caixa do jogador, o sistema não assume que o inimigo virou parte do PLAYER.

Fluxo:

```text
ENTITY conhecida aproxima
    ↓
memoriza LEFT / RIGHT / UP / DOWN
    ↓
contorno entra na caixa do PLAYER
    ↓
state = OCCLUDED
    ↓
caixa lógica é mantida na borda do PLAYER
    ↓
ID + lado + aparência limpa são preservados
    ↓
separação visual
    ↓
reacquire do mesmo ID
```

Durante `OCCLUDED`, a assinatura visual do contorno misturado PLAYER+inimigo não substitui a aparência limpa memorizada.

## Memória de lado relativo

Cada entidade guarda seu último lado confiável:

```text
LEFT
RIGHT
UP
DOWN
```

Essa memória é mantida durante oclusão e será usada futuramente pelo controlador v0.3b para decidir direção de recuperação sem depender apenas do frame atual.

## DORMANT / reacquisition

Depois de exceder o TTL ativo, uma identidade estabelecida não é imediatamente esquecida. Ela entra numa memória dormente por alguns segundos.

Padrões:

```text
reacquire TTL        = 5.0 s
reacquire distance   = 180 px
reacquire similarity = 0.82
```

Se um candidato compatível reaparecer, o mesmo `ENTITY ID` é restaurado em vez de criar um novo número.

## TARGET LOCK com hysteresis

```text
target-acquire = 55%
target-keep    = 38%
```

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
score < 38% ou identidade realmente expira
  ↓
solta o lock
```

## Enemy Score inicial

O score continua heurístico e combina persistência, movimento independente, aproximação, direção, distância, formato e memória de hostilidade. Ele continua sendo diagnóstico, não uma verdade final.

## Instalação

Na pasta `KageLink Installer/pc_agent`:

```powershell
.\.venv-kage-pilot\Scripts\python.exe -m pip install -r requirements.txt
```

## Executar

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py
```

Parâmetros adicionais úteis:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py `
  --background-similarity 0.88 `
  --background-min-hits 8 `
  --background-min-age 0.8 `
  --reacquire-ttl 5 `
  --reacquire-distance 180 `
  --reacquire-similarity 0.82 `
  --telemetry-seconds 2
```

Para comparar sem filtragem ambiental:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py --no-dynamic-background
```

Controles:

```text
clique esquerdo em Leafos = recalibrar PLAYER
Q ou ESC                  = sair
```

## Telemetria

Por padrão, o Observer imprime uma linha a cada 2 segundos:

```text
OBS t= 12.0s entities=15 bg_mature=8 bg_strong=3 suppressed=6 pruned=2 dormant=1 target=#042/VISIBLE/RIGHT/67.0%
```

Isso permite avaliar a evolução do fundo dinâmico e do TARGET ao longo do tempo, em vez de depender apenas de uma captura de tela.

## Critério de validação

A v0.3a será considerada validada quando:

1. `PLAYER #000` cobrir corretamente o sprite;
2. o player não nascer como `ENTITY`;
3. água/efeitos repetitivos forem progressivamente suprimidos;
4. o mesmo inimigo mantiver o mesmo ID por vários segundos;
5. `TARGET LOCK` sobreviver a pequenas oscilações;
6. contato com o player produzir `OCCLUDED` sem a caixa atravessar o PLAYER;
7. o lado relativo continuar estável durante a oclusão;
8. o mesmo ID puder ser recuperado depois de uma separação curta;
9. o movimento de câmera não virar uma avalanche de inimigos.

## Próxima etapa

Somente após validar essa percepção será criado o controlador v0.3b:

```text
SEARCH → APPROACH → MELEE → DISPLACED → RECOVER → POST_COMBAT
```

`LEFT`, `RIGHT`, `R +REP` e `H` serão decididos a partir do estado espacial e temporal do alvo, não por semelhança global entre frames.
