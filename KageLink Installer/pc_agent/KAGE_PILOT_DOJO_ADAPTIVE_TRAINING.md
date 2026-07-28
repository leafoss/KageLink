# Kage Pilot Dojo — Treinamento Adaptativo

**Data:** 28/07/2026  
**Status:** arquitetura futura; não implementada no motor validado  
**Dependência:** primeiro estabilizar e preparar para merge o loop canônico `kage_pilot_dojo.py` / v0.3i

## Objetivo

Adicionar uma camada de aprendizado que aperfeiçoe o treinamento no Dojo ao longo de várias rodadas reais, sem permitir que o aprendizado enfraqueça as regras de segurança já validadas.

A meta não é simplesmente vencer cada luta no menor tempo possível. O objetivo correto é maximizar o número de rodadas completas, estáveis e seguras por unidade de tempo.

```text
rodada completa =
  localizar/clicar no treinador
  + aguardar e iniciar luta
  + combater
  + reconhecer KO
  + retornar ao treinador
  + recuperar HP/Chakra
  + ficar READY
```

Exemplo:

```text
Estratégia A: combate 70 s + recuperação 20 s = ciclo 90 s
Estratégia B: combate 40 s + recuperação 65 s = ciclo 105 s
```

Mesmo vencendo mais rápido, a estratégia B é pior para treinamento contínuo.

## Função objetivo recomendada

Métrica principal:

```text
completed_rounds_per_hour
```

Equivalente para otimização por rodada:

```text
total_cycle_seconds =
  request_seconds
  + spawn_wait_seconds
  + combat_seconds
  + return_seconds
  + recovery_seconds
```

O otimizador deve minimizar a mediana e o p90 de `total_cycle_seconds`, não apenas `combat_seconds`.

Pontuação conceitual:

```text
reward =
  - total_cycle_seconds
  - safety_penalties
  - failure_penalties
  - instability_penalties
```

Penalidades fortes:

- timeout de combate;
- falha em reconhecer `has been Knocked-Out`;
- perda de primeiro plano;
- tecla persistente vazando após encerramento;
- segundo clique no treinador;
- uso de `V` ou `Y` durante combate;
- falha ao desligar `V` ou `Y`;
- não alcançar `READY`;
- necessidade de F12;
- erro de diálogo;
- ressincronizações repetidas na mesma rodada.

## Telemetria por rodada

Cada rodada deve produzir um registro imutável, preferencialmente JSONL, contendo:

```text
round_id
started_at
completed_at
result
opponent_name (quando disponível)
request_seconds
spawn_wait_seconds
combat_seconds
return_seconds
recovery_seconds
total_cycle_seconds
start_hp / end_combat_hp / ready_hp
start_chakra / end_combat_chakra / ready_chakra
h_attempts / h_confirmed_fires
directional_pulses
target_lost_seconds
engaged_search_seconds
motion_burst_hold_seconds
map_save_resync_count
obstacle_detour_count
y_fast_used
victory_chat_seen
ready_reached
foreground_losses
emergency_stop
policy_id
parameter_snapshot
```

Os modelos, históricos adaptativos e resultados locais devem ficar fora do Git, por exemplo:

```text
data/kage_pilot/adaptive/
```

Somente esquemas, código, exemplos sintéticos e documentação devem ser versionados.

## O que pode ser aprendido inicialmente

A primeira versão não deve gerar ações novas livremente. Ela deve escolher entre pequenas variações seguras de parâmetros já existentes.

Parâmetros candidatos:

- `h_stable_seconds`;
- `h_cooldown_seconds`;
- `h_min_score`;
- `face_refresh_seconds`;
- `move_confirm_frames`;
- `max_no_progress_seconds`;
- intervalos conservadores de reacquisição após ressincronização;
- limiares de uso de H dentro de faixas aprovadas.

Exemplo de políticas:

```text
policy_conservative:
  H menos frequente, maior confirmação

policy_balanced:
  parâmetros atuais validados

policy_aggressive_safe:
  H um pouco mais frequente, sem alterar gates de alvo e segurança
```

## O que nunca deve ser aprendido automaticamente

As seguintes invariantes permanecem fixas e fora do espaço de otimização:

- `has been Knocked-Out` como autoridade de fim de combate;
- liberação imediata de todas as teclas após KO;
- `R` como única tecla normalmente mantida no combate;
- setas e `H` como pulsos curtos;
- `V` proibido durante combate;
- `Y` proibido durante combate;
- `V` somente após treinador visualmente confirmado;
- clique único no treinador;
- botão `OK` acionado diretamente;
- recuperação mínima HP >= 90% e Chakra >= 50%;
- F12 como parada de emergência;
- fail-closed em perda de foco, diálogo ou chat;
- MotionBurstGuard, proteção contra água/partículas e prevenção de perseguição cega.

## Estratégia de aprendizado recomendada

### Etapa 1 — Observação passiva

Executar o motor validado sem alterar seu comportamento e apenas registrar métricas de 20 a 50 rodadas.

Objetivos:

- estabelecer baseline real;
- medir variação natural entre oponentes;
- identificar onde o tempo é gasto;
- descobrir se H reduz o ciclo total ou apenas transfere tempo para recuperação;
- medir frequência dos estados `ENGAGED_SEARCH` e `MOTION_BURST_HOLD`.

### Etapa 2 — Análise offline

Criar relatórios por política e por rodada:

- mediana e p90 do ciclo total;
- mediana de combate;
- mediana de recuperação;
- taxa de sucesso;
- número de falhas de segurança;
- eficiência marginal de cada uso de H;
- tempo parado aguardando alvo;
- impacto de ressincronizações.

Nenhuma mudança automática é aplicada nesta fase.

### Etapa 3 — Champion/Challenger em shadow mode

A política atual é a `champion`.

Uma política candidata (`challenger`) analisa cada frame e registra o que teria feito, mas não envia comandos. Depois comparamos:

- decisões divergentes;
- oportunidades adicionais de H;
- risco estimado;
- momentos de giro/movimento;
- provável impacto no ciclo.

Só políticas aprovadas em shadow mode podem receber autoridade real.

### Etapa 4 — Contextual bandit controlado

Para o primeiro aprendizado online, usar um bandit contextual entre poucas políticas pré-aprovadas, não reinforcement learning irrestrito.

Fluxo:

```text
selecionar policy_id seguro
→ executar uma rodada completa
→ medir reward e falhas
→ atualizar estatísticas
→ manter champion ou testar challenger
```

Cada candidato deve receber um número mínimo de rodadas antes de ser comparado. A promoção deve exigir:

- melhora estatisticamente consistente na mediana do ciclo;
- p90 não pior;
- taxa de sucesso não menor;
- zero nova violação de segurança;
- recuperação não excessivamente maior;
- ausência de vazamento de teclas.

### Etapa 5 — Promoção e rollback

Uma política só vira `champion` após aprovação automática conservadora e revisão humana.

Toda política precisa de:

```text
policy_id
created_at
parent_policy_id
parameter_snapshot
sample_count
median_cycle_seconds
p90_cycle_seconds
success_rate
safety_failure_count
status = candidate | champion | rejected | rolled_back
```

Qualquer falha grave causa rollback imediato para a última champion validada.

## Por que não usar reinforcement learning livre agora

O sistema atual já possui um modelo temporal de imitação (`TemporalCombatModel`) que aprende navegação e habilidade a partir de exemplos vitoriosos. Esse modelo é útil como referência futura e para shadow mode, mas não otimiza diretamente o tempo total da rodada nem considera explicitamente recuperação e segurança.

Um RL online livre teria riscos desnecessários:

- exploração física de ações ruins no jogo;
- possível uso incorreto de toggles;
- dificuldade de distinguir melhoria real de variação do oponente;
- regressões silenciosas em foco, chat e proteção de partículas;
- poucas amostras por configuração.

Por isso a evolução recomendada é:

```text
telemetria
→ análise offline
→ shadow mode
→ contextual bandit entre políticas seguras
→ somente depois avaliar aprendizado de política mais profundo
```

## Contexto usado pelo otimizador

Para não comparar rodadas incomparáveis, o seletor pode considerar:

- HP e Chakra no início da luta;
- posição relativa inicial do inimigo;
- tempo até o primeiro alvo validado;
- intensidade de partículas/movimento;
- presença de map-save resync;
- oponente/nome quando disponível;
- política usada na rodada anterior;
- histórico recente de sucesso e recuperação.

O contexto nunca autoriza quebrar invariantes de segurança.

## Integração futura com `DojoTrainingService`

A camada adaptativa deve ficar atrás da API pública e não dentro da UI.

Possível contrato futuro:

```python
config = DojoTrainingConfig(rounds=0, adaptive=True)
service.start(config)
status = service.snapshot()
```

Status adicionais possíveis:

```text
active_policy_id
baseline_cycle_seconds
rolling_cycle_seconds
completed_rounds
learning_mode = off | observe | shadow | adaptive
```

O toggle `Dojo` da aba Game apenas liga/desliga o serviço. Um controle separado e explícito deverá habilitar o aprendizado adaptativo; ele não deve ser ativado silenciosamente.

## Gate antes da implementação

Antes de começar esta camada:

- [ ] concluir polimento do release candidate atual;
- [ ] suíte completa em `OK`;
- [ ] validar o comando público `kage_pilot_dojo.py`;
- [ ] executar pelo menos 3 rodadas consecutivas;
- [ ] revisar e preparar o PR atual para merge;
- [ ] merge somente com aprovação explícita de Rafael;
- [ ] criar branch/PR separado para Adaptive Dojo Training;
- [ ] implementar primeiro somente telemetria passiva;
- [ ] não alterar automaticamente parâmetros durante as primeiras rodadas coletadas.

## Decisão

A camada adaptativa é recomendada, mas deve ser tratada como o próximo projeto sobre a baseline validada, não como parte do polimento final do PR atual.

O primeiro produto dessa camada não será um agente que muda sozinho. Será um registrador e analisador de rodadas capaz de responder com evidência:

- qual política vence mais rápido;
- qual política completa mais rodadas por hora;
- quanto cada uso adicional de H economiza no combate;
- quanto esse uso custa em recuperação;
- onde o agente permanece parado;
- quais mudanças são candidatas seguras para teste controlado.
