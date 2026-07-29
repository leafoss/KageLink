# Kage Pilot Dojo v0.3j — Merge-readiness record

**Date:** 2026-07-29  
**Branch:** `agent/kage-pilot-v0.3`  
**PR:** `#16`  
**Record state:** ready for review; merge still requires Rafael's explicit approval

## Canonical source

Under the KageLink Bible, GitHub is the only official source. The validated public path remains:

```text
kage_pilot_dojo.py
→ pc_agent.kage_pilot.DojoTrainingService
→ kage_pilot_loop_v03j.py
→ kage_pilot_live_v03k_round.py
```

Virtual environments, local configuration and runtime logs are not part of the official source.

## Long physical validation

The canonical execution completed all ten requested rounds:

```text
ROUND 10: COMPLETE / CONCLUIDA
DOJO_LOOP_FINISHED requested=10 processed=10 completed=10 finished_without_combat=0 failed=0 emergency_stopped=0
DOJO_FINAL phase=stopped completed=10 return_code=0
```

Result:

- 10 rounds requested;
- 10 rounds processed;
- 10 rounds completed;
- no round finished without combat;
- no failure;
- no emergency stop;
- exit code `0`.

## KO identity buffer — validated in-game

The real revived-body scenario occurred during the run:

```text
KO_CANDIDATE name="Jounin: Hasegawa, Suki" previous="Jounin: Hasegawa, Suki" visual_hits=2
KO_REJECTED reason=REPEATED_PREVIOUS_OPPONENT
TARGET_INVALIDATED reason=KO_IDENTITY_REJECTED
COMBAT_CONTINUES / COMBATE_CONTINUA
```

The runtime did not enter post-combat. It discarded the wrong target, continued fighting and later accepted the different opponent:

```text
KO_ACCEPTED reason=NEW_OPPONENT_KO previous="Jounin: Hasegawa, Suki" current="Jounin: Saito, Tozen"
VICTORY_CHAT / VITORIA_CHAT: Jounin: Saito, Tozen has been Knocked-Out
```

Validated contract:

```text
current KO name differs from the last accepted name
+ two current visual enemy observations in the round
= accepted victory
```

## Initial trainer acquisition — validated in-game

The possible-self-occlusion reveal maneuver also triggered:

```text
TRAINER_SCAN_HOLD phase=INITIAL_SCAN_HOLD
TRAINER_REVEAL_PROBE direction=right
TRAINER_SCAN_HOLD phase=REVEAL_SCAN_HOLD
TRAINER_VISUAL_CONFIRMED
TRAINER_CLICK_ONCE
```

The agent issued one lateral pulse, stopped, visually confirmed the trainer and clicked exactly once.

## Recovery and toggles

Rounds ended only after valid recovery. In round 10:

```text
POST Y_FAST_ON / Y_RAPIDO_LIGADO
POST Y_FAST_OFF / Y_RAPIDO_DESLIGADO
READY / PRONTO: HP and Chakra recovery thresholds reached
```

`V` remained dependent on current visual confirmation. `Y` was used only during meditation and disabled after the Chakra threshold was reached.

## Dialog gate

During this run, dialogs were found on the first check. The automated protection remains:

```text
1 trainer click
→ 1 initial check
→ up to 3 additional retries
→ no new click or search during retries
```

Failure after four checks consumes only the numbered round as `FINISHED_WITHOUT_COMBAT` and allows the next round to proceed.

## Preserved safety

- `R` is the only normally held combat key.
- Arrow keys and `H` are short pulses.
- `V` and `Y` are tap-only toggles and forbidden during combat.
- A rejected KO releases inputs, invalidates the target and continues combat.
- An accepted victory releases every input before post-combat.
- `MAP_SAVE_RESYNC` and `H_SETTLE_HOLD` remain absolute holds.
- F12 remains the emergency stop.
- Combat timeout stops the loop instead of advancing with a potentially live enemy.

## Repository hygiene

Local status contained only runtime artifacts:

```text
.venv-kage-pilot/
config.json
kage_pilot_live_test_*.jsonl
kage_pilot_shadow_test_*.jsonl
kage_pilot_loop_logs/
```

These paths were added to `.gitignore`. No local file was deleted. The official configuration remains:

```text
config/kage_pilot_dojo.json
```

## Public telemetry correction

Concentric-ring search telemetry also emitted `completed=N`, which could be mistaken by the facade for completed rounds. The public layer now accepts `completed=N` only from authoritative summaries:

```text
DOJO_LOOP_FINISHED
DOJO_LOOP_STOPPED
DOJO_FINAL
```

Lines such as this no longer update `completed_rounds`:

```text
TRAINER_SEARCH ... ring=3/29 completed=2 cells=19
```

Dedicated regression tests protect this contract.

## Final automated validation

Dedicated workflow on Windows Server 2025 / Python 3.11:

```text
67 targeted tests: OK
190 Kage Pilot tests: OK
318 complete PC Agent tests: OK
compilation: OK
canonical configuration: OK
```

Unified workflow:

```text
PC Agent Python: OK
KageLink.exe build and verification: OK
unified desktop smoke test: OK
Windows Setup: OK
Flutter analyze: OK
Flutter tests: OK
Android release APK: OK
```

## Documentation and traceability

- equivalent PT-BR and EN-US documentation;
- identifiable GitHub commits;
- PR updated with cause, changes, tests and physical validation;
- no official version stored in a ZIP or only in a local folder;
- historical scripts preserved to avoid risky consolidation in this PR.

## Final pre-merge state

- [x] real complete loop validated;
- [x] 10/10 rounds completed;
- [x] exactly one trainer click validated;
- [x] lateral trainer reveal validated;
- [x] repeated KO physically rejected;
- [x] correct opponent KO physically accepted;
- [x] return, meditation, `Y` and `READY` validated;
- [x] local artifacts protected by `.gitignore`;
- [x] round telemetry hardened;
- [x] PT-BR/EN-US documentation updated;
- [x] dedicated workflow completed successfully;
- [x] unified workflow completed successfully;
- [ ] merge only after Rafael's explicit approval.
