# Kage Pilot v0.3e — Loop completo do Dojo

Data: 28/07/2026

## Objetivo

Fechar um ciclo limitado e observável:

```text
READY junto ao treinador
→ clicar uma vez no treinador
→ localizar o diálogo #32770 + ListBox do processo do jogo
→ manter “Taijutsu Dojo Spar” (índice 0) selecionado
→ aguardar 10 segundos a partir do clique
→ Enter
→ aguardar 5 segundos
→ combate v0.3 validado
→ vitória pelo chat: “has been Knocked-Out”
→ retornar/procurar treinador
→ V para meditar
→ HP >= 90% e Chakra >= 50%
→ V para sair
→ READY
→ próxima rodada, se configurada
```

## Segurança

- F12 interrompe espera, combate e pós-combate.
- R e H nunca são usados durante retorno, busca, meditação ou diálogo.
- V continua sendo toggle: um toque entra, outro toque sai.
- O diálogo é identificado por processo do jogo, classe superior `#32770` e filho `ListBox`; HWND numérico não é persistido.
- O clique só ocorre com treinador visualmente confirmado e distância de grade `d <= 1`.
- A memória do treinador pode orientar deslocamento, mas nunca autoriza V ou clique.
- O loop padrão executa somente uma rodada.

## Obstáculos

Após um pulso direcional, o quadro seguinte mede:

- magnitude do movimento global da câmera;
- diferença média da arena capturada.

Duas leituras consecutivas sem movimento bloqueiam temporariamente aquela direção. A busca abandona o segmento atual do anel e testa a próxima direção. O bloqueio expira para permitir uma reavaliação posterior.

Uma semelhança parcial do treinador entre `0,80` e o threshold normal produz somente uma pausa curta. Ela não pode autorizar navegação, clique ou meditação e não pode congelar a busca indefinidamente.

## Executáveis

### Teste isolado de obstáculos

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_postcombat_live_test_v03e.py --seconds 90 --search-timeout 90
```

### Teste isolado de solicitação

Este teste inicia uma luta real e encerra após a espera de spawn:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo_request_test_v03e.py
```

### Uma rodada completa

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_loop_v03e.py --rounds 1
```

### Três rodadas completas

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_loop_v03e.py --rounds 3
```

### Até F12

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_loop_v03e.py --rounds 0
```

O modo até F12 só deve ser usado depois de várias rodadas limitadas bem-sucedidas.

## Arquivos principais

- `pc_agent/kage_pilot/post_combat_v03e.py`
- `pc_agent/kage_pilot/dojo_fight_v03e.py`
- `kage_pilot_postcombat_live_test_v03e.py`
- `kage_pilot_dojo_request_test_v03e.py`
- `kage_pilot_live_v03e_round.py`
- `kage_pilot_loop_v03e.py`
- `tests/test_kage_pilot_v03e_loop.py`
