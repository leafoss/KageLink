# Kage Pilot Dojo — Release Candidate

**Date:** 2026-07-28  
**Status:** release candidate; not merged  
**Validated functional baseline:** `kage_pilot_loop_v03i.py`

## Validated in-game milestone

The first complete round was successfully executed in Shinobi Story Online:

1. visually locate the Dojo Trainer;
2. click the trainer exactly once;
3. wait 5 seconds;
4. select `Taijutsu Dojo Spar` and click the real `OK` button directly;
5. wait 5 seconds for the opponent;
6. detect, fight and defeat the enemy;
7. recognize a new chat line containing `has been Knocked-Out`;
8. release every key immediately;
9. search for and return to the Dojo Trainer;
10. start meditation with one `V` tap;
11. wait for HP >= 90% and Chakra >= 50%;
12. turn persistent modes off and finish in `READY`;
13. report `ROUND 1: COMPLETE`.

The same execution also survived a map-save stall, discarded stale target/facing state and reacquired the opponent.

## Preserved safety policy

- `R` is the only continuously held combat key.
- Arrow keys and `H` are short pulses.
- `V` and `Y` are tap-only toggles.
- A new KO chat line is the only authority that ends combat.
- Victory releases every key before post-combat starts.
- Trainer memory may guide movement, but only a visual confirmation may authorize `V`.
- The trainer receives exactly one click per request.
- A missing dialog fails safely; no automatic second trainer click is allowed.
- `F12` remains the local emergency stop.

## Known conservative behavior

The agent may occasionally stand still and wait for the opponent to approach. This happens when there is no validated visual target or when MotionBurstGuard temporarily blocks movement and skills because the scene contains too many particles or moving regions.

This is currently safer than blind pursuit. It may be refined after a larger real-round sample without weakening protection against water, particles, map saving and stale identities.

## v0.3j candidate — facing during particle holds

A later round exposed a more specific case: perception correctly changed from `FACE_UP` to `MOVE_DOWN`/`FACE_DOWN`, but `MOTION_BURST_HOLD` also blocked every facing pulse. The character kept `R` active while physically facing the stale direction and combat took much longer.

The additive v0.3j correction is documented in:

```text
KAGE_PILOT_V0_3J_BURST_FACING.md
KAGE_PILOT_V0_3J_BURST_FACING.en.md
```

It allows only one facing pulse after two confirmations of a current visual adjacent target. Movement, pursuit and `H` remain blocked; `CONTACT_MEMORY`, `H_SETTLE_HOLD` and `MAP_SAVE_RESYNC` never receive the exception. v0.3j still requires real-game validation before replacing the v0.3i baseline in the public command.

## Stable public entry point

Use:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py --rounds 1
```

The public script runs the validated v0.3i engine in an isolated process. Scripts from `v03a` through `v03j` should be treated as historical/internal implementation during the release-candidate stage. The public command will be promoted to v0.3j only after the real facing-correction test succeeds.

## Future integration API

```python
from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService

service = DojoTrainingService()
service.start(DojoTrainingConfig(rounds=0))  # continuous until the toggle is disabled
status = service.snapshot()
service.stop()
```

Public contract:

- `DojoTrainingConfig`: normalized training parameters;
- `DojoTrainingService.start()`: starts only one instance;
- `DojoTrainingService.stop()`: requests process-group shutdown;
- `DojoTrainingService.snapshot()`: immutable UI-facing state;
- `DojoTrainingPhase`: `idle`, `starting`, `requesting`, `combat`, `victory`, `recovery`, `ready`, `stopping`, `stopped`, `error`.

## Future Game-tab toggle

The UI integration is not part of this release candidate. When implemented:

- `Dojo` toggle on: `start(DojoTrainingConfig(rounds=0))`;
- toggle off: `stop()`;
- status and messages must use the PT-BR/EN-US internationalization system;
- the UI must not import versioned modules or duplicate combat logic;
- only `DojoTrainingService` should cross the app/Kage Pilot boundary.

## Next milestone: adaptive training

The proposed architecture for learning to complete rounds faster and more reliably is documented separately in:

```text
KAGE_PILOT_DOJO_ADAPTIVE_TRAINING.md
KAGE_PILOT_DOJO_ADAPTIVE_TRAINING.en.md
```

The proposed primary metric is total round time and `completed_rounds_per_hour`, not combat time alone. The first implementation should be passive telemetry only; online learning belongs in a separate branch/PR after this baseline is merged.

## Pre-merge checklist

- [ ] targeted v0.3j tests finish with `OK`;
- [ ] full `test_kage_pilot*.py` suite finishes with `OK`;
- [ ] public service tests finish with `OK`;
- [ ] one real v0.3j round confirms `BURST_FACE_CORRECT` without enabling movement/H;
- [ ] promote the canonical command to v0.3j only after real validation;
- [ ] canonical `kage_pilot_dojo.py --rounds 1` completes a real round after promotion;
- [ ] run at least 3 consecutive rounds without key leakage into PowerShell;
- [ ] confirm exactly one trainer click in every round;
- [ ] confirm KO -> immediate release -> post-combat in every round;
- [ ] confirm `Y`, when needed, turns on and off exactly once;
- [ ] review untracked files and keep local models/templates out of Git;
- [ ] review the diff and PT-BR/EN-US documentation;
- [ ] remove draft status only after review;
- [ ] merge only after Rafael's explicit approval.

## Architectural decision

During polishing, the validated v0.3i implementation remains untouched. Behavioral corrections are added as small testable layers such as v0.3j. Physical consolidation of the versioned modules will be considered only after the public entry point is validated. This avoids introducing regressions into an in-game loop that already works.
