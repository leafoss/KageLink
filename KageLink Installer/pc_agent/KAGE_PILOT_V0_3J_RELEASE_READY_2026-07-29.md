# Kage Pilot Dojo v0.3j — Registro de prontidão para merge

**Data:** 29/07/2026  
**Branch:** `agent/kage-pilot-v0.3`  
**PR:** `#16`  
**Estado deste registro:** pronto para revisão; merge ainda exige aprovação explícita de Rafael

## Fonte canônica

Conforme a Bíblia do KageLink, o GitHub é a única fonte oficial. O caminho público validado permanece:

```text
kage_pilot_dojo.py
→ pc_agent.kage_pilot.DojoTrainingService
→ kage_pilot_loop_v03j.py
→ kage_pilot_live_v03k_round.py
```

Arquivos de ambiente virtual, configuração local e logs de execução não fazem parte da fonte oficial.

## Validação física longa

A execução canônica terminou todas as dez rodadas solicitadas:

```text
ROUND 10: COMPLETE / CONCLUIDA
DOJO_LOOP_FINISHED requested=10 processed=10 completed=10 finished_without_combat=0 failed=0 emergency_stopped=0
DOJO_FINAL phase=stopped completed=10 return_code=0
```

Resultado:

- 10 rodadas solicitadas;
- 10 rodadas processadas;
- 10 rodadas concluídas;
- nenhuma rodada sem combate;
- nenhuma falha;
- nenhuma parada de emergência;
- código de saída `0`.

## Buffer de identidade do KO — validado no jogo

O cenário real de corpo reanimado ocorreu durante a execução:

```text
KO_CANDIDATE name="Jounin: Hasegawa, Suki" previous="Jounin: Hasegawa, Suki" visual_hits=2
KO_REJECTED reason=REPEATED_PREVIOUS_OPPONENT
TARGET_INVALIDATED reason=KO_IDENTITY_REJECTED
COMBAT_CONTINUES / COMBATE_CONTINUA
```

O runtime não entrou no pós-combate. Ele descartou o alvo incorreto, continuou lutando e depois aceitou o adversário diferente:

```text
KO_ACCEPTED reason=NEW_OPPONENT_KO previous="Jounin: Hasegawa, Suki" current="Jounin: Saito, Tozen"
VICTORY_CHAT / VITORIA_CHAT: Jounin: Saito, Tozen has been Knocked-Out
```

Contrato validado:

```text
nome atual do KO diferente do último nome aceito
+ duas observações visuais atuais de inimigo na rodada
= vitória aceita
```

## Aquisição inicial do treinador — validada no jogo

A manobra de revelação por possível oclusão também ocorreu:

```text
TRAINER_SCAN_HOLD phase=INITIAL_SCAN_HOLD
TRAINER_REVEAL_PROBE direction=right
TRAINER_SCAN_HOLD phase=REVEAL_SCAN_HOLD
TRAINER_VISUAL_CONFIRMED
TRAINER_CLICK_ONCE
```

O agente executou um único pulso lateral, parou, confirmou visualmente o treinador e realizou exatamente um clique.

## Recuperação e toggles

As rodadas terminaram somente após recuperação válida. Na rodada 10:

```text
POST Y_FAST_ON / Y_RAPIDO_LIGADO
POST Y_FAST_OFF / Y_RAPIDO_DESLIGADO
READY / PRONTO: HP and Chakra recovery thresholds reached
```

`V` permaneceu dependente de confirmação visual atual. `Y` foi usado apenas durante meditação e desligado ao alcançar o threshold de Chakra.

## Gate do diálogo

Durante esta execução, os diálogos foram encontrados na primeira verificação. A proteção continua automatizada:

```text
1 clique no treinador
→ 1 verificação inicial
→ até 3 retries adicionais
→ nenhum novo clique ou nova busca durante retries
```

Uma falha após quatro verificações consome somente a rodada numerada como `FINISHED_WITHOUT_COMBAT` e permite seguir para a próxima.

## Segurança preservada

- `R` é a única tecla normalmente mantida durante combate.
- Setas e `H` são pulsos curtos.
- `V` e `Y` são toggles por toque e proibidos durante combate.
- KO rejeitado libera inputs, invalida alvo e continua o combate.
- Vitória aceita libera todos os inputs antes do pós-combate.
- `MAP_SAVE_RESYNC` e `H_SETTLE_HOLD` permanecem bloqueios absolutos.
- F12 permanece parada de emergência.
- Timeout de combate interrompe o loop em vez de avançar com inimigo possivelmente vivo.

## Higiene do repositório

O status local mostrou apenas artefatos de execução:

```text
.venv-kage-pilot/
config.json
kage_pilot_live_test_*.jsonl
kage_pilot_shadow_test_*.jsonl
kage_pilot_loop_logs/
```

Esses caminhos foram adicionados ao `.gitignore`. Nenhum arquivo local foi apagado. A configuração oficial continua em:

```text
config/kage_pilot_dojo.json
```

## Correção da telemetria pública

A busca em anéis também emitia `completed=N`, que podia ser confundido pelo facade com número de rodadas concluídas. A camada pública agora aceita `completed=N` somente em resumos autoritativos:

```text
DOJO_LOOP_FINISHED
DOJO_LOOP_STOPPED
DOJO_FINAL
```

Linhas como esta não alteram mais `completed_rounds`:

```text
TRAINER_SEARCH ... ring=3/29 completed=2 cells=19
```

O contrato foi protegido por testes de regressão dedicados.

## Validação automatizada final

Workflow dedicado em Windows Server 2025 / Python 3.11:

```text
67 testes direcionados: OK
190 testes Kage Pilot: OK
318 testes completos PC Agent: OK
compilação: OK
configuração canônica: OK
```

Workflow unificado:

```text
PC Agent Python: OK
KageLink.exe: build e verificação OK
smoke test do desktop unificado: OK
Windows Setup: OK
Flutter analyze: OK
Flutter tests: OK
Android release APK: OK
```

## Documentação e rastreabilidade

- documentação equivalente em PT-BR e EN-US;
- commits identificáveis no GitHub;
- PR atualizado com causa, mudanças, testes e validação física;
- nenhuma versão oficial em ZIP ou apenas na pasta local;
- scripts históricos preservados para evitar consolidação arriscada neste PR.

## Estado final pré-merge

- [x] loop completo real validado;
- [x] 10/10 rodadas concluídas;
- [x] clique único no treinador validado;
- [x] revelação lateral do treinador validada;
- [x] KO repetido rejeitado fisicamente;
- [x] KO do adversário correto aceito fisicamente;
- [x] retorno, meditação, `Y` e `READY` validados;
- [x] artefatos locais protegidos por `.gitignore`;
- [x] telemetria de rodadas endurecida;
- [x] documentação PT-BR/EN-US atualizada;
- [x] workflow dedicado completo em sucesso;
- [x] workflow unificado completo em sucesso;
- [ ] merge somente após aprovação explícita de Rafael.
