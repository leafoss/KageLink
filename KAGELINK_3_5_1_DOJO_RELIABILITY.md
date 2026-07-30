# KageLink 3.5.1 — Confiabilidade do Dojo Trainer

[English](KAGELINK_3_5_1_DOJO_RELIABILITY.en.md)

## Escopo

A versão 3.5.1 altera somente três áreas:

1. journal por sessão, preservado apenas quando houver erro ou encerramento incompleto;
2. posição relativa visual, keyframes, relocalização e retorno ao ponto confirmado do Trainer;
3. página Desktop responsiva com as abas Resumo, Configurações, Imagens e Logs.

O detector do Trainer, thresholds, clique, diálogo, combate, KO, recuperação, F12, GAME interlock, templates e comunicação Android permanecem com seus contratos anteriores.

## Journal

Local:

```text
%LOCALAPPDATA%\KageLink\logs\dojo
```

Fluxo:

```text
início → .active com flush por evento
sucesso → resumo + remoção do .active
erro → dojo_error_*.txt
crash/energia → dojo_incomplete_*.txt na próxima inicialização
```

A aba Logs mostra somente o último diagnóstico e botões para abrir arquivo/pasta.

## Posição visual

A fonte de verdade é o movimento observado:

```text
movimento no mundo = movimento do jogador na tela - movimento do cenário na tela
```

Os comandos enviados representam intenção. Um empurrão, teleport ou jutsu pode alterar X/Y mesmo sem comando. Um comando bloqueado não altera X/Y.

Estados:

```text
KNOWN       posição utilizável
UNCERTAIN   evidência insuficiente para retorno longo
LOST        continuidade perdida; coordenadas não podem ser inventadas
```

## Keyframes e relocalização

O motor mantém um conjunto limitado de referências visuais associadas a X/Y. Quando a continuidade é perdida, o personagem para, libera teclas e tenta reconhecer a região atual. A restauração exige score mínimo e margem sobre o segundo candidato.

Um teleport sem cenário comum e sem keyframe conhecido permanece `LOST`; o sistema não fabrica um vetor de retorno.

## Retorno em malha fechada

A origem `(0,0)` é definida quando o Trainer é visualmente confirmado. Depois do combate:

```text
parar e estabilizar
→ relocalizar se necessário
→ escolher um passo que reduza a distância
→ medir o deslocamento real
→ atualizar posição
→ recalcular
→ scan estacionário próximo da origem
→ busca local curta
→ busca em anéis existente
```

Empurrões durante o retorno causam replanejamento. Loops possuem timeout, limite de passos e interrupção por F12/Stop.

## Desktop

Abas:

- **Resumo:** motor, fase, progresso, rodada, localização resumida, controle e últimas ações;
- **Configurações:** somente parâmetros já existentes;
- **Imagens:** 64×64 e 32×32, com prévias nítidas e persistentes;
- **Logs:** último erro, horário, resumo e caminhos.

O layout usa grid responsivo, inicialização imediata, `after_idle` e resize com debounce. Não maximiza ou minimiza a janela artificialmente.

## Teste físico

1. instalar Setup 3.5.1;
2. confirmar abertura correta em janela restaurada e maximizada;
3. confirmar Settings por último;
4. validar templates 32×32 e 64×64;
5. concluir uma sessão sem gerar erro permanente;
6. provocar erro controlado e abrir o `.txt` pela aba Logs;
7. observar X/Y ao andar;
8. observar deslocamento externo por empurrão/jutsu;
9. testar perda e relocalização em região já mapeada;
10. testar retorno compensando novo deslocamento;
11. validar busca local e fallback em anéis;
12. validar F12, Stop e GAME interlock;
13. validar APK conectado ao mesmo build.

A PR permanece Draft e não pode ser mesclada sem autorização explícita de Rafael.
