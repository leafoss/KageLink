# Kage Pilot Dojo — Release Candidate v0.3j

**Date:** 2026-07-28  
**Status:** prepared for final pre-merge validation; not merged  
**Validated functional baseline:** `kage_pilot_loop_v03j.py`  
**Public entry point:** `kage_pilot_dojo.py`

## Validated in-game milestone

v0.3j completed a real Shinobi Story Online round:

1. visually located the Dojo Trainer;
2. clicked the trainer exactly once;
3. waited for the configured delay;
4. selected `Taijutsu Dojo Spar` and directly activated the real `OK` button;
5. waited for the opponent;
6. detected, faced and fought using base attack and guarded `H`;
7. recognized `has been Knocked-Out` in chat;
8. released every key;
9. returned to the trainer from `d=10` to `d=1`;
10. started meditation with one `V` tap;
11. enabled `Y` when HP reached 96% while Chakra remained at 32%;
12. disabled `Y` when Chakra reached 52%;
13. reached `READY`;
14. exited with `ROUND 1: COMPLETE` and return code `0`.

The user rated v0.3j combat as excellent and approved its behavior for promotion to the public entry point.

## Preserved safety policy

- `R` is the only normally held combat key.
- Arrow keys and `H` are short pulses.
- `V` and `Y` are tap-only toggles.
- A new KO chat line is the only combat-end authority.
- Victory releases every key before post-combat.
- The trainer receives exactly one click per request.
- The real `OK` button is activated directly in the exact dialog.
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

The file controls:

- rounds;
- wait after trainer click;
- dialog timeout;
- wait after the `OK` button;
- combat timeout;
- post-combat timeout;
- trainer-search timeout;
- target HP and Chakra;
- guarded `H` usage;
- visual threshold;
- log directory.

Percentages may be increased but cannot be lowered below `90% HP / 50% Chakra`.

Show the effective configuration:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py --show-config
```

Run with the default configuration:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py
```

PowerShell arguments temporarily override JSON values.

## Future integration API

```python
from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingService

service = DojoTrainingService()
service.start(DojoTrainingConfig(rounds=0))
status = service.snapshot()
service.stop()
```

The future Game tab will use only this API. It must not import versioned modules or duplicate combat logic. Visible text must use the PT-BR/EN-US internationalization system.

## Tests executed in this review

A dedicated workflow was added:

```text
.github/workflows/kage-pilot-v03.yml
```

On the official Windows Server 2025 runner with Python 3.11, the following passed:

- dependency installation;
- compilation of all Kage Pilot modules;
- targeted release-candidate tests;
- the full `test_kage_pilot*.py` suite;
- `kage_pilot_dojo.py --show-config` validation;
- the full PC Agent suite: **283 tests, all `OK`**.

The first complete-suite run exposed an old LeafOS test pinned to the literal date `2026-07-26`. The behavior was correct, but the test failed when run on `2026-07-28`. Its assertion was changed to validate the stable `YYYY-MM-DD_001` contract, and the next complete suite passed.

CI validates code, configuration and packaging, but does not replace physical Windows/BYOND execution against the real game window.

## Bible compliance

- GitHub remains the canonical technical source.
- Every change ends in an identifiable commit.
- Relevant documentation exists in PT-BR and EN-US.
- Configuration belongs to the service/domain layer, not the future UI.
- The app receives a small stable public boundary.
- Behavioral changes were additive and validated in-game.
- An automated Windows gate now protects merge readiness.
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
- [x] KO -> release -> post-combat confirmed;
- [x] `Y` enabled and disabled exactly once when required;
- [x] public entry point promoted to v0.3j;
- [x] canonical JSON configuration added;
- [x] PT-BR/EN-US documentation reviewed;
- [x] targeted Windows tests in `OK`;
- [x] full `test_kage_pilot*.py` Windows suite in `OK`;
- [x] full PC Agent suite: 283 tests in `OK`;
- [x] `kage_pilot_dojo.py --show-config` validated in Windows CI;
- [x] PC Agent compilation and packaging in `OK`;
- [ ] run 3 consecutive rounds through the canonical command in the real game;
- [ ] confirm no key leakage into PowerShell during those three rounds;
- [ ] review `git status` and untracked files on the user's computer;
- [ ] remove PR draft state after the real-game gates above;
- [ ] merge only after Rafael's explicit approval.

## Architectural decision

Scripts `v03a` through `v03j` remain internal history during this release candidate. The stable contract is:

```text
kage_pilot_dojo.py
→ DojoTrainingConfig
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
```

Physical consolidation of historical modules may happen after merge in a separate PR, avoiding regression risk in the baseline that already works in-game.
