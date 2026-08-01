# Kage Combat Lab e `grid_focus_v2`

## Estado desta intervenção

Esta intervenção iniciou no head:

```text
6dfa5281357eb52abec4cf37f2c080a84f987dda
```

A PR #23 deve permanecer aberta, em Draft e sem merge. A estratégia experimental não será transformada em padrão do instalador antes da aprovação dos gates offline e da validação física explícita.

## Limitação da nova captura recebida

O arquivo abaixo foi recebido como evidência do teste físico mais recente:

```text
round_001_20260731_195348_6508.avi
```

No ambiente usado para esta intervenção, o arquivo foi materializado corretamente, mas o executor local de vídeo falhou antes de decodificar os quadros. Portanto, nenhuma conclusão visual específica sobre essa nova gravação é apresentada como fato neste documento. A arquitetura foi revisada com base na regressão física já documentada, no runtime real da PR e no prompt de intervenção fornecido por Rafael.

Isso não reduz o valor do novo vídeo: ele deve ser preservado para comparação humana e, quando houver pacote RAW de caixa-preta, para correlação temporal. O AVI processado não é tratado como replay RAW determinístico.

## Auditoria do runtime anterior

Antes da alteração, o processo iniciado por `kage_pilot_round.py` instalava a cadeia abaixo:

```text
kage_pilot_round.py
→ kage_pilot_visual_return.py
→ bridges de resolução
→ import de kage_pilot_live_v0351_round.py
→ cadeia histórica v03k/v03j/v03i/v03h/v03g/v03e/v03
→ install_combat_target_bridge
→ install_combat_runtime_hardening
→ install_runtime_guard
→ bridges de meditação, geometria e recursos
→ install_runtime_lab
→ install_round_video_performance_guard
→ runtime.main
```

### Mapa do runtime anterior

| Arquivo | Classe ou função | Responsabilidade | Classe-base real | Substituição posterior | Configuração efetiva | Risco identificado |
|---|---|---|---|---|---|---|
| `kage_pilot_round.py` | `main()` | Entrada isolada da rodada | — | Nenhuma | Argumentos do processo pai | Resultado dependia da ordem de imports |
| `kage_pilot_visual_return.py` | `main()` | Instalação das bridges | Runtime histórico | Recorder ainda alterava `process` | Ordem procedural | Uma bridge posterior podia substituir a classe testada |
| `kage_pilot_live_v03e_round.py` | `MovementAndAnchorObserver` | Combate e posição para retorno | Observer histórico v03 | v03i e v03k | Configuração v03 | Combate e retorno compartilham herança antiga |
| `kage_pilot_live_v03i_round.py` | `MapSaveResyncObserver` | Resync após stall ou scene spike | `MovementAndAnchorObserver` | v03k | `frame_gap=1.25s` | Resync global altera tracker, alvo e grid |
| `kage_pilot_live_v03k_round.py` | `OpponentAwareObserver` | Gate de identidade do KO | Observer vindo de v03j/v03i | Bridge persistente | Duas evidências para KO | Captura bases antes das bridges posteriores |
| `combat_target_runtime_v351.py` | `CombatFilteredTracker` | Filtro preliminar de efeitos | Tracker histórico | Nenhuma | JSON de combate | Classe local criada dentro da instalação |
| `combat_target_runtime_v351.py` | `PersistentCombatTargetObserver` | Identidade persistente | `OpponentAwareObserver` | Hardening posterior | 48/96 px e memória temporal | Um rebind aceito atualizava posição, tamanho, aparência e direção de uma vez |
| `dojo_combat_runtime_hardening_v351.py` | `PhysicallyHardenedCombatObserver` | Limitação emergencial | `PersistentCombatTargetObserver` | Recorder alterava `process` | 0,9/1,2/3,0 s e score 0,62 | Outra subclasse local, sem autoridade espacial própria |
| `grid_target_observer_v03d.py` | `TileCalibratedGridTargetObserver` | Seleção preliminar no grid | Observer de pés | Envolvido pela cadeia acima | Confirmação em dois frames | Ainda aceitava estado `OCCLUDED` em partes do contato/rebind |
| `dojo_vision_lab_v351.py` | `install_runtime_lab()` | AVI diagnóstico | Monkeypatch da classe final | Última alteração do observer | 2 fps | Gravador processado, não laboratório ou replay RAW |

### Causa estrutural confirmada no código

O runtime possuía duas geometrias concorrentes:

```text
grid e distância lógica → âncora dos pés
memória persistente → track.center
```

Uma associação visual aceita podia renovar e deslocar a identidade usando o centro de um blob, enquanto a decisão de distância usava a célula dos pés. A segunda camada de hardening limitava movimento perigoso, mas não impedia a hipótese interna de ser contaminada.

## Instalação canônica atual

A entrada da rodada agora possui um único ponto de instalação de combate:

```text
install_combat_strategy_runtime(runtime)
```

As duas instalações antigas não fazem mais parte do entrypoint canônico:

```text
install_combat_target_bridge(runtime)        # removida do entrypoint
install_combat_runtime_hardening(runtime)    # removida do entrypoint
```

As implementações históricas permanecem no repositório para testes, compatibilidade e investigação. Elas não são empilhadas sobre a estratégia selecionada no processo canônico.

### Classes concretas registradas

```text
CanonicalCombatTracker
CanonicalCombatObserver
CanonicalCombatDecisionEngine
CanonicalCombatPlanner
CanonicalCombatVictoryWatcher
```

No início de cada processo, após todas as bridges, é emitido uma única vez:

```text
DOJO_COMBAT_RUNTIME_PROVENANCE
```

O evento contém a estratégia, classes e módulos concretos, caminho da configuração e parâmetros efetivos. Isso prova o runtime empacotado em vez de apenas provar uma classe isolada nos testes.

## Estratégias explícitas

A factory disponibiliza:

```text
legacy_safe
persistent_hardened
grid_focus_v2
```

### `legacy_safe`

Fallback comparativo que representa aquisição imediata orientada pelo melhor track visível. Permanece disponível para diagnóstico e comparação; não é promovido como solução nova.

### `persistent_hardened`

Política conservadora equivalente à proteção emergencial: somente observações limpas, rebind confirmado, previsão limitada e ausência de perseguição cega. Continua sendo o padrão configurado enquanto `grid_focus_v2` não recebe aprovação física.

### `grid_focus_v2`

Estratégia experimental cuja identidade principal é uma hipótese espacial:

```text
pixels
→ contorno
→ âncora dos pés
→ célula lógica
→ hipótese espacial
→ Combat Target
```

## Modelo de observação espacial

Cada observação contém:

```text
anchor_cell
bbox_cells
body_cell_coverage
visible
body_like
contaminated
enemy_score
appearance_signature
body_size
classification
```

Classificações:

```text
CLEAN_SINGLE_CELL_BODY
BODY_SPANS_BORDER
MULTI_CELL_EFFECT
TARGET_EFFECT_CONTAMINATED
CAMERA_OR_SCENE_MOTION
UNKNOWN_BLOB
```

Somente observações visuais limpas podem atualizar:

```text
confirmed_cell
predicted_cell
appearance_signature
body_size
confirmed_direction
confidence
last_clean_seen_at
```

Atividade contaminada pode atualizar somente:

```text
last_any_activity_at
possible_presence_in_locked_cell
contamination
```

Ela não altera posição, direção, aparência, tamanho, confiança positiva ou timeout limpo.

## Aquisição em duas fases

### `ATTENTION`

Uma observação limpa plausível cria apenas uma hipótese de atenção. Nesse estado:

```text
R pode permanecer ativo
facing pode apontar para a região quando seguro
H é proibido
movimento é proibido
Combat Target persistente ainda não existe
```

### `TARGET_CONFIRMED`

A identidade nasce após duas observações coerentes na mesma hipótese espacial, com visão atual, body gate aprovado, âncora válida, score adequado e ausência de contaminação.

## Foco perceptivo após o lock

```text
GLOBAL_DISCOVERY
LOCKED_CELL_FOCUS
PREDICTED_CELL_FOCUS
LOCAL_GRID_RECOVERY
GLOBAL_RECOVERY
COMBAT_DISABLED
```

Após o primeiro lock, candidatos distantes podem continuar existindo para diagnóstico e segurança global, mas não competem pela identidade. A busca autoritativa começa na célula confirmada, avança para uma única célula prevista e depois para a vizinhança 3×3. A busca global retorna somente após perda limpa real.

## Rebind espacial em quarentena

Um novo `track_id` não recebe a identidade imediatamente. Tracks diferentes na mesma célula alimentam uma única `GridRebindHypothesis`.

Enquanto o rebind está pendente:

```text
confirmed_cell não muda
confirmed_direction não muda
appearance_signature não muda
body_size não muda
confidence não aumenta
hard timeout limpo não é renovado
movimento e H permanecem sem nova autoridade
```

A confirmação exige duas observações limpas e coerentes na mesma célula ou célula adjacente fisicamente plausível.

A mudança de célula do mesmo track também passa por quarentena. Isso evita que uma animação, sombra ou bbox parcialmente contaminada desloque a identidade após um único frame.

## Previsão discreta

A previsão é limitada a:

```text
confirmed_cell
ou
uma das oito células vizinhas
```

Não existe velocidade herdada entre tracks. Uma nova identidade lógica reinicia a continuidade da previsão. Saltos de múltiplas células dentro do mesmo `combat_target_id` são falhas de gate.

## Adjacência e `MELEE_LOCK`

Contato usa distância de Chebyshev:

```python
max(abs(dx_cells), abs(dy_cells)) <= 1
```

Assim, todas as oito células vizinhas são adjacentes.

`MELEE_LOCK` exige um corpo visual limpo e atual em célula adjacente. Sem visão limpa:

```text
MELEE_LOCK
→ MELEE_HOLD durante grace mínima
→ LOCAL_GRID_RECOVERY
```

Memória sozinha não autoriza movimento ou H.

## Contexto visual do próprio ataque

Quando H é realmente autorizado, o planner registra `AttackVisualContext` com origem, direção, corredor esperado e expiração. Durante essa janela, observações no corredor podem ser classificadas como contaminadas e não criam nem rebidam identidade.

## Encerramento de combate

Após KO aceito:

```text
combat_phase = POST_COMBAT
perception_scope = COMBAT_DISABLED
Combat Target = None
pending rebind = None
attention = None
track creation = disabled
movement authority = false
attack authority = false
```

O watcher também solicita reset do planner e do observer. Nenhum blob posterior ao KO pode criar um novo alvo.

## Kage Combat Lab

O pacote independente está em:

```text
pc_agent/kage_pilot/combat_lab/
```

Ele não importa nem envia teclado, mouse ou comandos ao BYOND. Possui:

- simulador lógico por grid;
- comparação das três estratégias;
- replay JSON determinístico;
- relatórios JSON e texto;
- caixa-preta RAW bounded e assíncrona;
- CLI offline.

Execução local:

```powershell
python -m pc_agent.kage_pilot.combat_lab --strategy grid_focus_v2 --json combat-report.json --text combat-report.txt
```

## Cenários determinísticos

O laboratório cobre 25 cenários, incluindo:

1. quatro direções cardinais;
2. quatro diagonais;
3. inimigo parado;
4. inimigo cruzando e sobrepondo o jogador;
5. perdas de três e dez frames;
6. efeito horizontal;
7. blob de três células;
8. blob falso próximo e na célula antiga;
9. mudança de track na mesma célula;
10. mudança impossível de célula;
11. dois candidatos na mesma região;
12. deslocamento de câmera;
13. knockback do jogador;
14. KO;
15. blob depois do KO;
16. segundo adversário após perda real do primeiro.

## Caixa-preta RAW

A caixa-preta é opt-in:

```text
KAGELINK_COMBAT_BLACK_BOX=1
```

Ela mantém um buffer bounded de arena RAW, timestamps, células, candidatos, tracks, observações, snapshot, decisão, comando, contexto de ataque e KO. O loop crítico não renderiza nem codifica vídeo.

Materialização ocorre somente:

- em retorno de falha da rodada;
- mediante `KAGELINK_COMBAT_BLACK_BOX_MATERIALIZE=1`;
- ou por solicitação explícita do runtime de debug.

O worker assíncrono grava:

```text
raw_arena_frames.npz
replay.json
```

## Gate de release offline

O teste `test_combat_lab_release_gate_v351.py` exige:

```text
todos os cenários grid_focus_v2 = PASS
false_rebinds = 0
multi_cell_blobs_promoted = 0
post_ko_targets = 0
time_in_melee_lock_without_clean_visual = 0
prediction_cell_jumps = 0
replay repetível
padrão configurado continua persistent_hardened
três estratégias continuam comparáveis
```

O resultado final da CI e as métricas consolidadas devem ser registrados após o head estabilizar.

## Gate físico futuro

Mesmo após aprovação offline, `grid_focus_v2` não deve ser automaticamente convertido em padrão. O próximo teste físico deverá confirmar:

```text
um Combat Target lógico por adversário
zero promoções multicélula
zero novos alvos após KO
nenhum MELEE_LOCK prolongado sem visual limpo
nenhuma direção alterada por rebind pendente
nenhum salto de previsão de múltiplas células
foco local após lock
busca global somente após perda real
```

A CI prova consistência lógica, compilação e empacotamento. Ela não substitui a validação física no Windows/BYOND.
