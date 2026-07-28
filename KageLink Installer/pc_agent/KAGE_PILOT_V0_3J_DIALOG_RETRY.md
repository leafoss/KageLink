# Kage Pilot v0.3j — Retry seguro do diálogo do Dojo

**Data:** 28/07/2026  
**Status:** implementação e testes automatizados aprovados; validação física pendente  
**Escopo:** somente o gate treinador → diálogo → botão `OK`

## Causa raiz

Na terceira rodada de uma execução configurada para dez rodadas, o treinador foi localizado e recebeu corretamente um único clique. O diálogo não foi encontrado dentro da primeira janela de observação e `DOJO_DIALOG_NOT_FOUND` foi propagado como `DojoFightRequestError` fatal.

O orquestrador tratava qualquer falha de solicitação como motivo para executar `break`, encerrando o loop completo depois de duas rodadas concluídas.

```text
ROUND 3: TRAINER_CLICK_ONCE
ROUND 3: DOJO_REQUEST_FAILED: DOJO_DIALOG_NOT_FOUND
DOJO_LOOP_STOPPED completed=2
```

A causa não estava na detecção do treinador, no clique, no combate ou no chat. O problema era a combinação de:

1. apenas uma oportunidade de localizar o diálogo depois do clique;
2. ausência de um resultado recuperável para “rodada finalizada sem combate”;
3. tratamento global fatal de `DOJO_DIALOG_NOT_FOUND`.

## Fonte de verdade escolhida

A correção foi aplicada no caminho canônico já usado pelo release candidate:

```text
kage_pilot_dojo.py
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
→ kage_pilot_loop_v03g.py
→ dojo_fight_v03i.py
```

Responsabilidades:

- `dojo_fight_v03i.py`: clique único, esperas, revalidação do diálogo, clique no `OK` e resultado recuperável;
- `kage_pilot_loop_v03g.py`: semântica das rodadas, continuação do loop e contadores;
- `kage_pilot_loop_v03j.py`: ativa a política robusta no entrypoint validado;
- `kage_pilot_dojo.py` e `DojoTrainingService`: permanecem como contrato público, sem duplicar o gate.

Nenhuma segunda implementação paralela foi criada.

## Regra absoluta de clique único

Por rodada:

```text
trainer_clicks <= 1
```

Depois de `TRAINER_CLICK_ONCE`, o código não pode:

- pesquisar novamente o treinador;
- mover-se para reencontrá-lo;
- clicar novamente no sprite;
- repetir a solicitação de spar;
- reutilizar coordenadas do treinador.

Todos os retries atuam exclusivamente sobre o diálogo já solicitado.

## Novo fluxo

Com `--dialog-delay 5` e o padrão `--dialog-retries 3`:

```text
SEARCH_TRAINER
→ VISUAL_CONFIRM
→ TRAINER_CLICK_ONCE
→ release_all

→ WAIT 5s
→ DIALOG CHECK 1/4

→ WAIT 5s
→ DIALOG CHECK 2/4

→ WAIT 5s
→ DIALOG CHECK 3/4

→ WAIT 5s
→ DIALOG CHECK 4/4
```

A conta é sempre:

```text
1 verificação inicial
+ 3 retries
= 4 verificações totais
```

Cada verificação:

1. mantém todos os inputs liberados;
2. procura novamente a janela pelo processo do jogo;
3. valida a classe `#32770`;
4. valida `ListBox`, quantidade mínima de opções e controle `OK` visível/habilitado;
5. reenumera o diálogo imediatamente antes do clique;
6. confirma que os HWNDs continuam válidos dentro de `click_first_option_ok`;
7. clica somente no controle `OK` atual.

Não são usadas coordenadas fixas, HWNDs históricos ou o match da tentativa anterior.

## Estados e resultados

### Sucesso

```text
TRAINER_CLICK_ONCE
→ DOJO_DIALOG_WAIT/RETRY_WAIT
→ DOJO_DIALOG_CONFIRMED
→ DOJO_DIALOG_OK_CLICKED
→ DOJO_REQUEST_OK
→ WAITING_FOR_SPAWN
→ START COMBAT RUNTIME
```

`DOJO_REQUEST_OK` só existe depois de confirmação atual do diálogo e clique válido no botão `OK`.

### Quatro verificações sem diálogo

```text
TRAINER_CLICK_ONCE
→ quatro esperas/verificações
→ ABORTED reason=DOJO_DIALOG_NOT_FOUND trainer_clicks=1 dialog_attempts=4
→ FINISHED_WITHOUT_COMBAT
→ próxima rodada
```

A rodada consome seu número. Em `--rounds 10`, uma falha na rodada 3 produz rodadas 1 até 10; nunca é criada uma rodada 11 compensatória.

### F12

Em qualquer espera:

```text
F12
→ interromper espera
→ release_all
→ EMERGENCY_STOP
→ encerrar o programa completo
```

## Contadores finais

O resumo agora separa:

```text
requested
processed
completed
finished_without_combat
failed
emergency_stopped
```

Exemplo de uma falha recuperável na rodada 3:

```text
DOJO_LOOP_FINISHED requested=10 processed=10 completed=9 finished_without_combat=1 failed=0 emergency_stopped=0
```

## Exemplo — sucesso na quarta verificação

```text
ROUND 3: TRAINER_CLICK_ONCE score=0.939 d=1
ROUND 3: DOJO_DIALOG_WAIT attempt=1/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=1/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=2/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=2/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=3/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=3/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=4/4 delay=5.0
ROUND 3: DOJO_DIALOG_CONFIRMED attempt=4/4 hwnd=...
ROUND 3: DOJO_DIALOG_OK_CLICKED attempt=4/4 hwnd=...
ROUND 3: DOJO_REQUEST_OK trainer_clicks=1 dialog_attempts=4
ROUND 3: WAITING_FOR_SPAWN delay=5.0
ROUND 3: START COMBAT RUNTIME
```

## Exemplo — rodada encerrada sem combate

```text
ROUND 3: TRAINER_CLICK_ONCE score=0.939 d=1
ROUND 3: DOJO_DIALOG_WAIT attempt=1/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=1/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=2/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=2/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=3/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=3/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=4/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=4/4
ROUND 3: ABORTED reason=DOJO_DIALOG_NOT_FOUND trainer_clicks=1 dialog_attempts=4
ROUND 3: FINISHED_WITHOUT_COMBAT
ROUND 4: SEARCH AND REQUEST TAIJUTSU DOJO SPAR
```

## Arquivos alterados

```text
pc_agent/kage_pilot/dojo_fight_v03i.py
kage_pilot_loop_v03g.py
kage_pilot_loop_v03j.py
tests/test_kage_pilot_dojo_dialog_retry.py
.github/workflows/kage-pilot-v03.yml
```

## Testes adicionados

1. diálogo encontrado após a espera inicial;
2. diálogo encontrado após um retry;
3. diálogo encontrado após dois retries;
4. diálogo encontrado após três retries;
5. diálogo nunca aparece;
6. garantia de apenas um clique no treinador;
7. F12 durante espera;
8. HWND desaparece antes do clique no `OK`;
9. rodada 3 falha em dez rodadas e o loop processa até a rodada 10.

## Resultado automatizado

Runner oficial Windows Server 2025, Python 3.11:

```text
41 testes direcionados: OK
164 testes Kage Pilot: OK
292 testes completos PC Agent: OK
compilação: OK
configuração canônica: OK
```

## Escopo preservado

Não foram alterados:

- detecção visual do treinador;
- visão/tracking de inimigos;
- lógica de combate e facing;
- `MotionBurstGuard`;
- uso de `H`;
- KO autoritativo pelo chat;
- retorno ao treinador;
- meditação, HP, Chakra e `Y`;
- política de obstáculos;
- runtime de combate.

## Gate restante

A correção ainda precisa ser validada no jogo real em nova execução de várias rodadas. O PR permanece em draft e nenhum merge está autorizado.
