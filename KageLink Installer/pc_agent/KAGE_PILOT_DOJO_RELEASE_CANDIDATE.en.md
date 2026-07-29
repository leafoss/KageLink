# Kage Pilot Dojo — Release Candidate v0.3j

**Date:** 2026-07-28  
**Status:** prepared for renewed physical pre-merge validation; not merged  
**Functional baseline:** `kage_pilot_loop_v03j.py`  
**Public entry point:** `kage_pilot_dojo.py`

## Validated in-game milestone

v0.3j completed real Shinobi Story Online rounds with:

1. visual Dojo Trainer location;
2. exactly one trainer click;
3. `Taijutsu Dojo Spar` selection through the real `OK` button;
4. detection, facing, base attack and guarded `H`;
5. chat recognition of `has been Knocked-Out`;
6. immediate release of all keys;
7. return to the trainer;
8. meditation through the `V` toggle;
9. recovery to HP >= 90% and Chakra >= 50%;
10. `Y` enabled and disabled exactly once when required;
11. completion in `READY` and `ROUND COMPLETE`.

The user rated v0.3j combat as excellent.

## Failure found during long validation

In a ten-round run, rounds 1 and 2 completed. In round 3, the trainer was found and clicked exactly once, but the dialog did not appear during the first observation window:

```text
ROUND 3: TRAINER_CLICK_ONCE
ROUND 3: DOJO_REQUEST_FAILED: DOJO_DIALOG_NOT_FOUND
DOJO_LOOP_STOPPED completed=2
```

The issue was fatal handling of a temporary dialog failure. The policy was corrected without changing vision, combat, facing, KO, return or recovery.

Detailed documentation:

```text
KAGE_PILOT_V0_3J_DIALOG_RETRY.md
KAGE_PILOT_V0_3J_DIALOG_RETRY.en.md
```

## Robust trainer → dialog gate

The current policy is:

```text
1 trainer click
→ initial wait
→ check 1/4
→ additional wait → check 2/4
→ additional wait → check 3/4
→ additional wait → check 4/4
```

With defaults:

```text
--dialog-delay 5
--dialog-retries 3
```

The calculation is:

```text
1 initial check + 3 retries = 4 total checks
```

Rules:

- after `TRAINER_CLICK_ONCE`, never search for, move toward or click the trainer again;
- every retry acts only on the already-requested dialog;
- the dialog and `OK` control are re-enumerated and revalidated before clicking;
- no HWND or coordinate from a previous attempt is reused;
- all inputs remain released during waits;
- F12 interrupts waits;
- combat starts only after `DOJO_DIALOG_CONFIRMED` and `DOJO_DIALOG_OK_CLICKED`;
- four failures end only the current round in `FINISHED_WITHOUT_COMBAT`;
- the next round uses the next number without a compensating round.

## Preserved safety policy

- `R` is the only normally held combat key.
- Arrow keys and `H` are short pulses.
- `V` and `Y` are tap-only toggles.
- A new KO chat line is the only combat-end authority.
- Victory releases every key before post-combat.
- The trainer receives at most one click per round.
- The real `OK` button is activated in the current validated dialog.
- `V` requires visual trainer confirmation.
- `V` and `Y` are forbidden during combat.
- `MAP_SAVE_RESYNC` still releases every key.
- `H_SETTLE_HOLD` remains absolute.
- F12 remains the local emergency stop.

## Facing during particle holds

v0.3j preserves `MotionBurstGuard` while adding a narrow exception that prevents the character from remaining physically faced away from an adjacent opponent:

- current visual target only;
- `MELEE` with `d <= 1` only;
- two confirmations of the same target/direction;
- at most one pulse per burst episode;
- no movement, pursuit or `H` authority;
- never from isolated `CONTACT_MEMORY`;
- never during `MAP_SAVE_RESYNC` or `H_SETTLE_HOLD`.

Details:

```text
KAGE_PILOT_V0_3J_BURST_FACING.md
KAGE_PILOT_V0_3J_BURST_FACING.en.md
```

## Public configuration

Basic settings live in:

```text
config/kage_pilot_dojo.json
```

Documentation:

```text
KAGE_PILOT_DOJO_CONFIGURATION.md
KAGE_PILOT_DOJO_CONFIGURATION.en.md
```

The file controls rounds, waits, timeouts, recovery, guarded `H`, visual threshold and logs. Percentages may be increased but cannot be lowered below `90% HP / 50% Chakra`.

Show the effective configuration:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py --show-config
```

Run with the default configuration:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py
```

## Future integration API

```python
from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService

service = DojoTrainingService()
service.start(DojoTrainingConfig(rounds=0))
status = service.snapshot()
service.stop()
```

The future Game tab will use only this API. It must not import versioned modules or duplicate combat logic. Visible text must use the PT-BR/EN-US internationalization system.

## Tests executed

Dedicated workflow:

```text
.github/workflows/kage-pilot-v03.yml
```

On the official Windows Server 2025 runner with Python 3.11, after the dialog correction:

```text
41 targeted tests: OK
164 Kage Pilot tests: OK
292 complete PC Agent tests: OK
compilation: OK
canonical configuration: OK
```

The nine new tests cover success on checks 1, 2, 3 and 4, absent dialog, one-click guarantee, F12, disappearing HWND and a round-3 failure that does not interrupt a ten-round run.

CI validates code and configuration, but it does not replace physical Windows/BYOND execution against the real game window.

## Bible compliance

- GitHub remains the canonical technical source.
- Every change ends in an identifiable commit.
- Relevant documentation exists in PT-BR and EN-US.
- The policy is centralized in the canonical release-candidate path.
- No combat logic is duplicated at the future app boundary.
- An automated Windows gate protects merge readiness.
- No merge occurs without Rafael's explicit approval.

## Next milestone: adaptive training

It remains documented separately in:

```text
KAGE_PILOT_DOJO_ADAPTIVE_TRAINING.md
KAGE_PILOT_DOJO_ADAPTIVE_TRAINING.en.md
```

The first future stage is passive telemetry. Online learning is not part of this release candidate.

## Final pre-merge checklist

- [x] first complete loop validated in-game;
- [x] v0.3j approved in a real round;
- [x] exactly one trainer click confirmed;
- [x] KO → release → post-combat confirmed;
- [x] `Y` enabled and disabled exactly once when required;
- [x] round-3 dialog failure diagnosed;
- [x] one initial wait + three retries implemented;
- [x] a no-dialog round continues to the next round;
- [x] nine dialog regression tests added;
- [x] 41 targeted tests in `OK`;
- [x] 164 Kage Pilot tests in `OK`;
- [x] 292 complete PC Agent tests in `OK`;
- [ ] physically validate dialog retry in the real game;
- [ ] run another consecutive multi-round test through the canonical command;
- [ ] confirm no second trainer click;
- [ ] confirm no key leakage into PowerShell;
- [ ] review `git status` and untracked files;
- [ ] remove PR draft state after the real-game gates;
- [ ] merge only after Rafael's explicit approval.

## Architectural decision

Scripts `v03a` through `v03j` remain internal history during this release candidate. The stable contract remains:

```text
kage_pilot_dojo.py
→ DojoTrainingConfig
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
```

Physical consolidation of historical modules may happen after merge in a separate PR, avoiding regression risk in the baseline that already works in-game.
