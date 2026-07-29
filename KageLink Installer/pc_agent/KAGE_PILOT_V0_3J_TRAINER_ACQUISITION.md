# Kage Pilot v0.3j — Aquisição estacionária do treinador

**Data:** 29/07/2026  
**Status:** implementação automatizada; validação física pendente

## Falha observada

Em uma nova execução de 20 rodadas, a rodada 1 não registrou nenhuma confirmação visual do treinador. O buscador aguardou apenas brevemente e começou a percorrer anéis concêntricos, chegando a 19 células lógicas antes de a janela perder o foco.

```text
TRAINER_SEARCH state=SEARCH_WAIT
TRAINER_SEARCH state=SEARCH_LEADER move=up
...
ring=3/29 cells=19
DOJO_REQUEST_STOPPED_FATAL: GameControlError: FOREGROUND_LOST
```

A comparação de commits confirmou que o hotfix do buffer de KO não alterou o detector nem a busca do treinador. A falha expôs uma fragilidade anterior: a busca podia enviar pulsos quase continuamente antes de obter duas imagens estáveis do treinador.

O cenário é especialmente provável quando o personagem começa sobreposto ao treinador e oculta parte do sprite.

## Novo fluxo

```text
ativar janela do jogo
→ liberar todos os inputs
→ 1,5 s de aquisição visual estacionária
→ se não houver treinador: um único pulso lateral para a direita
→ 0,75 s de aquisição estacionária
→ busca em anéis somente se ainda necessário
→ após cada pulso: 0,35 s parado para nova leitura visual
```

## Invariantes

- nenhum clique ocorre antes de duas confirmações visuais atuais;
- o pulso de revelação ocorre no máximo uma vez por solicitação;
- o pulso de revelação é lateral, nunca `up` ou `down`;
- durante as pausas, todas as teclas ficam liberadas;
- a busca em anéis continua disponível para início distante do treinador;
- F12 continua interrompendo imediatamente;
- perda de foreground continua encerrando a solicitação com segurança;
- o buffer de KO, combate, pós-combate, recuperação e diálogo não foram alterados.

## Telemetria

```text
TRAINER_SCAN_HOLD phase=INITIAL_SCAN_HOLD
TRAINER_REVEAL_PROBE direction=right
TRAINER_SCAN_HOLD phase=REVEAL_SCAN_HOLD
TRAINER_SEARCH ...
TRAINER_SCAN_HOLD phase=POST_MOVE_SCAN_HOLD
TRAINER_VISUAL_CONFIRM hits=1/2
TRAINER_VISUAL_CONFIRMED
```

## Arquivos

```text
pc_agent/kage_pilot/trainer_search_v03k.py
pc_agent/kage_pilot/dojo_fight_v03i.py
tests/test_kage_pilot_v03k_trainer_search_gate.py
.github/workflows/kage-pilot-v03.yml
```

## Gate restante

Validar no jogo começando com o personagem diretamente abaixo ou parcialmente sobreposto ao treinador. O PR continua em draft e sem merge.
