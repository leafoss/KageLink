# Kage Pilot v0.1

[English](KAGE_PILOT.en.md)

O **Kage Pilot** é um subsistema experimental e local do KageLink para aprender ações de combate demonstradas pelo jogador e reproduzi-las no Dojo de `Shinobi Story Online`.

> Status v0.1: pipeline funcional para gravação → dataset → treino → Pilot → ciclo do Dojo. O modelo inicial é deliberadamente simples e deve ser refinado com dados reais do Dojo.

## Arquitetura

```text
KAGE PILOT v0.1
│
├── Recorder
│   ├── captura HWND existente do KageLink
│   ├── teclado físico
│   ├── mouse
│   └── timestamp
│
├── Dataset
│   ├── frames JPEG
│   ├── snapshots de ações
│   ├── blocos de ação + duração
│   └── vitória / derrota
│
├── Combat Learner
│   └── clone comportamental por protótipos visuais
│
├── Pilot
│   └── prevê e aplica o estado do teclado
│
└── Dojo Manager
    ├── sequência para iniciar
    ├── Pilot durante o combate
    ├── detector visual de vitória/derrota
    ├── sequência de descanso
    └── repetição
```

O Dojo Manager é determinístico. A IA controla somente a parte que deve ser aprendida: **o combate**.

## Segurança e isolamento

- O Pilot usa a captura específica da janela `Shinobi Story Online` já existente no KageLink.
- O controle reutiliza `GameInputController`, incluindo foco da janela e proteção contra teclas presas.
- Cliques automáticos usam coordenadas normalizadas dentro da janela do jogo.
- O Pilot não executa programas nem comandos genéricos do sistema.
- Nenhuma mudança é necessária no Interpreter, chat, RAW, Memory Reviewer, Android ou protocolo atual.

## 1. Gravar demonstrações

No diretório `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py record
```

Durante a gravação:

```text
F11 = encerra a luta como vitória
F12 = encerra a luta como derrota
F10 = encerra o Recorder
```

Depois de F11/F12, uma nova sessão começa automaticamente. Assim é possível jogar várias lutas seguidas.

Por padrão, os dados ficam em:

```text
%LOCALAPPDATA%\KageLink PC Agent\data\kage_pilot\sessions\
```

Cada luta contém:

```text
<session>/
├── manifest.json
├── samples.jsonl
├── actions.jsonl
└── frames/
    ├── 000000.jpg
    ├── 000001.jpg
    └── ...
```

`samples.jsonl` mantém o estado do teclado/mouse junto ao frame e timestamp. `actions.jsonl` consolida estados consecutivos e registra `duration_ms`.

## 2. Treinar o primeiro Combat Learner

```powershell
python kage_pilot.py train --model kage_pilot_model.json
```

Por padrão, apenas sessões marcadas como `victory` treinam o modelo. Isso evita ensinar derrotas como comportamento desejado.

Para incluir derrotas experimentalmente:

```powershell
python kage_pilot.py train --model kage_pilot_model.json --include-defeats
```

A v0.1 aprende **estados do teclado** a partir de uma representação visual compacta do frame. O mouse é gravado no dataset, mas ainda não faz parte da política de combate aprendida.

## 3. Testar somente o combate

```powershell
python kage_pilot.py pilot --model kage_pilot_model.json --seconds 60
```

O Pilot captura a janela, escolhe uma ação e passa apenas as teclas previstas ao controlador seguro do KageLink.

## 4. Calibrar o Dojo Manager

Primeiro crie a configuração:

```powershell
python kage_pilot.py init-config --output dojo_config.json
```

O arquivo contém:

- `start_sequence`: clique/teclas usados para falar com o NPC e iniciar;
- `rest_sequence`: ações usadas após o combate;
- `victory`: template visual obrigatório;
- `defeat`: template visual opcional;
- `rested`: template visual opcional;
- tempos máximos e atrasos de segurança.

### Capturar um template

Com a tela desejada visível:

```powershell
python kage_pilot.py capture-template --output templates/victory.png --region 0.35 0.15 0.30 0.15
```

A região é normalizada:

```text
X Y LARGURA ALTURA
0.0 ───────────── 1.0
```

Escolha uma região pequena e estável que diferencie claramente vitória, derrota ou personagem recuperado.

**Não use as coordenadas do arquivo exemplo sem calibrar no seu Dojo.** Elas são somente placeholders seguros.

## 5. Rodar o ciclo completo

```powershell
python kage_pilot.py dojo --model kage_pilot_model.json --config dojo_config.json --cycles 10
```

Fluxo:

```text
iniciar treino
    ↓
aguardar arena
    ↓
Pilot luta
    ↓
vitória detectada
    ↓
soltar todas as teclas
    ↓
descansar
    ↓
recuperado / tempo concluído
    ↓
próxima luta
```

Se o combate exceder `combat_timeout_seconds`, o Manager solta as teclas e encerra a sequência em `timeout` em vez de continuar indefinidamente.

## Testes da v0.1

O teste automatizado cobre:

1. criação e finalização de sessão;
2. frames, teclado, mouse e timestamps;
3. geração de blocos de ação com duração;
4. treino e persistência do modelo;
5. previsão de ações distintas em imagens sintéticas;
6. detector visual por template;
7. ciclo `iniciar → Pilot → vitória → descanso` com componentes simulados.

Comando:

```powershell
python -m unittest tests.test_kage_pilot -v
```

## Limite de validação

Os testes automatizados validam o software e o ciclo de controle, mas não substituem a validação no BYOND. O ambiente de desenvolvimento automatizado não possui Windows + `Shinobi Story Online`, portanto a captura HWND real, o `SendInput` e os templates do Dojo precisam de uma rodada curta de calibração no seu PC antes de considerar o Pilot validado em jogo.

Essa separação é intencional: a v0.1 não inventa sprites, coordenadas ou telas que ainda não foram observadas.
