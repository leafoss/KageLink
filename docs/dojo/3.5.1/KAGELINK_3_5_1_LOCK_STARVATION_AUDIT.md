# KageLink 3.5.1 — auditoria incremental de lock starvation

## Estado inicial

```text
PR: #23
branch: fix/3.5.1-dojo-reliability
head inicial: 16dad2d6f386f2ede3d992557502e132d28ddbe8
estado: OPEN / DRAFT / SEM MERGE
```

Esta auditoria precede qualquer alteração comportamental solicitada no ciclo de correção de lock starvation.

## Sintoma físico que governa a intervenção

```text
visual target permanece sobre o adversário
→ visual track continua existindo
→ existem candidatos VISIBLE/OCCLUDED em d=0/d=1
→ Combat Target não é criado ou não é mantido
→ combate fica inoperante
```

A correção deve aumentar a aderência depois da confirmação sem reabrir a regressão anterior, em que qualquer blob próximo ao jogador podia renovar a identidade.

## Ordem real do runtime canônico

```text
kage_pilot_round.py
→ kage_pilot_visual_return.py
→ install_resolution_independent_dojo
→ install_resolution_scope_compat
→ install_resolution_gate_slots_compat
→ install_visual_position_guard
→ import kage_pilot_live_v0351_round
→ activate_round_resolution_detector
→ ensure_safe_meditation_timeout
→ install_combat_strategy_runtime
→ install_runtime_guard
→ install_meditation_timeout_bridge
→ install_runtime_geometry_bridge
→ install_resource_quantization_bridge
→ install_chakra_recovery_bridge
→ install_combat_strategy_vision
→ install_runtime_lab
→ install_round_video_performance_guard
→ emit_runtime_provenance
→ runtime.main
```

`install_combat_strategy_runtime` é o único ponto canônico de instalação do combate. As bridges históricas `install_combat_target_bridge` e `install_combat_runtime_hardening` continuam disponíveis como compatibilidade, mas não são empilhadas pelo entrypoint real.

## Mapa das classes e riscos

| Arquivo | Classe/função | Responsabilidade | Classe-base real | Substituição posterior | Configuração efetiva | Estados tratados | Risco identificado |
|---|---|---|---|---|---|---|---|
| `combat_strategy_v351.py` | `CombatTargetStrategy` | Contrato, snapshot, métricas e políticas comuns | `ABC` | Estratégias concretas | `CombatStrategyConfig` | `ATTENTION`, `VISIBLE`, `LOCAL_REBIND`, `LOST`; modos internos | `appearance_similarity` concede evidência positiva quando aparência não existe |
| `combat_strategy_v351.py` | `PersistentHardenedStrategy` | Fallback conservador atual | `CombatTargetStrategy` | Registro explícito | seção `combat_strategy` | aquisição limpa, rebind pendente, hard loss | aquisição imediata e score com bônus de aparência ausente |
| `grid_focus_v2_strategy_v351.py` | `GridFocusV2SpatialStrategy` | Autoridade espacial experimental | `GridFocusV2Strategy` | Registro em `STRATEGY_TYPES` | mesma configuração | `ATTENTION`, lock, scopes, quarentena | oclusão do mesmo tracker ainda não preserva presença aderente; hard timeout usa apenas visual limpo |
| `combat_strategy_runtime_v351.py` | `StrategyObserverMixin.process` | Converte todos os tracks em `GridObservation` e chama a estratégia | observer histórico v03 | `CanonicalCombatObserver` final | estratégia carregada do JSON | `POST_COMBAT` e snapshots da estratégia | o body gate pode classificar o target base como inválido, mas todas as observações já são encaminhadas; falta watchdog de starvation |
| `combat_strategy_runtime_v351.py` | `StrategyDecisionEngineMixin` | Converte snapshot em decisão | engine histórico v03 | `CanonicalCombatDecisionEngine` | snapshot atual | `ATTENTION`, `MELEE_LOCK`, `MELEE_HOLD`, `LOCAL_GRID_RECOVERY`, `GLOBAL_RECOVERY`, `POST_COMBAT` | estado desconhecido deve permanecer fail-closed |
| `combat_strategy_runtime_v351.py` | `StrategyControlPlannerMixin` | Autoridade final de MOVE/H/R | planner histórico v03 | `CanonicalCombatPlanner` | decisão atual | `POST_COMBAT`, autoridade visual, pursuit | correto por padrão fail-closed, mas depende de snapshot coerente |
| `combat_target_memory_v351.py` | `choose_local_rebind` | Fallback histórico de memória em pixels | nenhuma | usado somente por compatibilidade | `CombatTargetConfig` | `VISIBLE/OCCLUDED` | gate aceita candidato longe da previsão se estiver perto do jogador |
| `combat_target_memory_v351.py` | `rebind_score` | Score do fallback histórico | nenhuma | nenhuma | pesos legados | contexto visual | aparência/movimento ausentes recebem bônus positivos |
| `grid_target_observer_v03c.py` | `FrameAlignedGridTargetObserver` | Métricas por âncora dos pés | observer estrito histórico | `TileCalibratedGridTargetObserver` | `tile_size` de runtime | nenhum enum de target | deve aceitar somente 32 ou 64 pixels RAW |
| `grid_target_observer_v03d.py` | `TileCalibratedGridTargetObserver` | Grid, contato e seleção histórica | `FrameAlignedGridTargetObserver` | base do observer canônico | `tile_size` passado pelo runtime | `VISIBLE/OCCLUDED/LOST` do tracker | construtor ainda aceita qualquer float positivo |
| `dojo_resolution_bridge_v351.py` | `DojoGeometry` / `apply_tracker_geometry` | Autoridade de modo e odometria | dataclass/função | bridge de geometria | modo 32/64 persistido | não se aplica | valida 32/64, mas não há objeto canônico compartilhado pelo combate |
| `kage_pilot_visual_return.py` | `main` | Entry point e ordem das bridges | função | nenhuma | config persistida | não compara estados | deve instalar a autoridade canônica de grid antes do combate |
| `dojo_combat_strategy_vision_v351.py` | renderização | Overlay de estratégia | renderer do Lab | wrapper diagnóstico | snapshot | todos por texto | precisa expor starvation e geometria canônica |
| `combat_lab/replay.py` | replay offline | Determinismo sem input | nenhuma | nenhuma | fixture | snapshots serializados | AVI processado não é replay RAW literal |
| `combat_lab/scenarios.py` | cenários | Casos determinísticos | nenhuma | runner | estratégia selecionada | estados internos | faltam fixtures específicas do incidente de starvation |

## Consumidores auditados

Os consumidores que tratam estado, modo, fase ou scope são:

```text
CombatTargetStrategy._movement_mode
CombatTargetStrategy._snapshot
LegacySafeStrategy.update
PersistentHardenedStrategy.update
GridFocusV2Strategy.update
GridFocusV2SpatialStrategy.update
StrategyObserverMixin.process
StrategyDecisionEngineMixin.decide
StrategyControlPlannerMixin.plan
StrategyVictoryWatcherMixin.poll
dojo_combat_strategy_vision_v351.annotate_strategy_diagnostics
combat_black_box_runtime_v351
combat_lab/replay.py
combat_lab/runner.py
suítes test_combat_strategy_v351.py e test_grid_focus_spatial_authority_v351.py
```

Política obrigatória para qualquer estado desconhecido:

```text
R permitido durante combate
MOVE bloqueado
H bloqueado
troca de target bloqueada
```

## Causas mínimas confirmadas antes da mudança

1. `choose_local_rebind` usa uma condição equivalente a posição prevista **OU** proximidade do jogador, permitindo um candidato espúrio perto do jogador.
2. O fallback histórico concede `appearance_score=0.45` e `movement_score=0.65` sem evidência real.
3. O runtime canônico já envia todos os tracks à estratégia, mas a política de limpeza pode ignorar o visual target persistente por sobreposição/oclusão.
4. `grid_focus_v2` usa célula como autoridade, porém não possui uma presença aderente explícita para o mesmo tracker durante contato ocluído.
5. O construtor do grid ainda aceita `tile_size` arbitrário; 32 e 64 precisam ser o único domínio válido.
6. Não existe telemetria explícita para a condição “visual target persistente sem Combat Target”.

## Sequência de implementação

```text
Fase 1A: autoridade imutável do grid 32/64
Fase 1B: corrigir fallback de rebind e evidência ausente
Fase 1C: watchdog de lock starvation
Fase 2: ATTENTION/overlap sem aquisição falsa em d=0
Fase 3: aderência forte ao mesmo tracker durante oclusão curta
Fase 4: rebind exclusivamente por célula e quarentena
Fase 5: replay aproximado do incidente e gates finais
```

Cada fase deve ter testes e métricas próprias antes da seguinte.

A PR permanece aberta, em Draft e sem merge.
