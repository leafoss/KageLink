# Kage Pilot

[Português](KAGE_PILOT.md) · [KageLink Development Bible](AGENTS.en.md)

**Kage Pilot** is KageLink's local experimental subsystem for demonstration recording, visual perception, combat control, and repeated Dojo training in **Shinobi Story Online**.

This file is the canonical EN-US documentation. Old documents named after `V0_1`, `V0_2`, `V0_3`, `V03J`, dates, or hotfixes belong to Git history and must not return as competing active documentation.

## Current state

- **Single public entry point:** `KageLink Installer/pc_agent/kage_pilot.py`.
- **Validated Dojo command:** `python kage_pilot.py dojo`.
- **Official configuration:** `KageLink Installer/pc_agent/config/kage_pilot_dojo.json`.
- **Public service:** `pc_agent.kage_pilot.DojoTrainingService`.
- **Workflow:** `.github/workflows/kage-pilot.yml`.
- **Status:** the Dojo baseline was physically validated and merged through PR #16 on July 29, 2026.

The recorded long run completed:

```text
DOJO_LOOP_FINISHED requested=10 processed=10 completed=10
finished_without_combat=0 failed=0 emergency_stopped=0
```

## Organization rule

Kage Pilot has **one public surface** while remaining modular internally.

```text
kage_pilot.py
    ├── dojo                         # validated canonical flow
    ├── record / mark                # dataset
    ├── train / train-v2             # training
    ├── pilot / pilot-v2             # policy execution
    ├── capture-template
    ├── init-config
    └── dojo-v2                      # earlier experimental tool
```

Internal modules must be named after responsibilities, not versions. New versions belong in commits, tags, releases, and changelogs—not new files such as `final2`, `v03l`, or `hotfix_new`.

## Functional architecture

```text
game-specific HWND capture
        ↓
visual perception and temporal state
        ↓
target selection and combat decision
        ↓
safe key planner
        ↓
validated Windows control
        ↓
chat-confirmed KO
        ↓
trainer return and recovery
        ↓
next round
```

Learning may select approved policies or parameters, but it must never weaken safety gates.

## Run Dojo training

From `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py dojo
```

Ten-round example:

```powershell
python kage_pilot.py dojo `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

Show effective configuration without starting:

```powershell
python kage_pilot.py dojo --show-config
```

`--rounds 0` runs continuously until an explicit stop or F12.

## Protected state machine

```text
ROUND_START
→ SEARCH_TRAINER
→ CONFIRM_TRAINER
→ CLICK_TRAINER_ONCE
→ WAIT_DIALOG
→ CHECK_DIALOG
→ CLICK_DIALOG_OK
→ WAIT_SPAWN
→ COMBAT_ACTIVE
→ KO_CONFIRMED
→ RETURN_TO_TRAINER
→ RECOVERY
→ ROUND_COMPLETE
```

Alternative exits:

```text
retryable failure
→ end only the attempt or round
→ preserve the parent loop when safe

F12
→ EMERGENCY_STOP
→ release every input
→ stop the loop
```

## Absolute trainer contract

```text
trainer_clicks_per_round <= 1
```

After `TRAINER_CLICK_ONCE`, dialog waits or retries must never:

- click the trainer again;
- search for another trainer to repeat the request;
- move the character to restart the interaction;
- issue a second spar request.

The dialog gate uses:

```text
1 trainer click
→ 1 initial check
→ up to 3 additional checks
→ no repeated click
```

If the dialog does not appear after four checks, the round becomes `FINISHED_WITHOUT_COMBAT` and the next round may begin.

## Visual trainer acquisition

Visual perception creates a candidate; it does not directly authorize a click.

The validated flow requires:

1. initial scan;
2. stable visual confirmation;
3. one short lateral reveal when the player may hide the trainer;
4. renewed visual confirmation;
5. exactly one click.

Old position memory never authorizes `V` by itself.

## Combat

Permanent rules:

- `R` is the only normally held combat key;
- arrows and `H` are short pulses;
- `V` and `Y` are tap-only toggles and forbidden during combat;
- lost target, focus, or visual authority must reduce action rather than increase aggression;
- `MAP_SAVE_RESYNC` and `H_SETTLE_HOLD` remain absolute holds;
- particle-time facing correction is limited to a current, adjacent, confirmed visual target;
- every error or transition must release pending keys.

## KO authority

Combat completion authority remains the real line:

```text
has been Knocked-Out
```

Cross-round protection keeps the last accepted opponent. A KO with the same name as the previous opponent is rejected until sufficient current visual evidence supports a different opponent.

Validated flow:

```text
repeated previous-opponent KO
→ release_all
→ invalidate current target
→ continue combat
→ reacquire target

new name + current visual evidence
→ accept victory
→ release_all
→ start post-combat
```

## Return and recovery

A round ends only after the character returns to a safe recovery state.

Configuration cannot reduce these floors:

```text
HP >= 90%
Chakra >= 50%
```

- `V` may be tapped only after current visual trainer confirmation.
- `Y` may remain on only during meditation and must be turned off after the threshold.
- recovery timeout must not report false success.

## Round counters

```text
requested
processed
completed
finished_without_combat
failed
emergency_stopped
```

A no-combat round consumes its number. `--rounds 10` processes at most numbered rounds 1 through 10; it must not silently create round 11 as compensation.

## Configuration

The official JSON exposes only understandable safe values:

- rounds;
- waits and timeouts;
- recovery targets above protected floors;
- H enablement;
- trainer threshold;
- log directory.

Invalid configuration fails closed with an identifiable error. Unknown keys are not silently ignored.

Safety invariants are not configurable.

## Dataset and earlier tools

The single entry point preserves recording and learning commands:

```powershell
python kage_pilot.py record
python kage_pilot.py mark
python kage_pilot.py train --model kage_pilot_model.json
python kage_pilot.py train-v2 --model kage_pilot_temporal.json
python kage_pilot.py pilot --model kage_pilot_model.json --seconds 60
python kage_pilot.py pilot-v2 --model kage_pilot_temporal.json --seconds 60
```

Personal data and runtime artifacts remain outside Git:

```text
.venv-kage-pilot/
data/kage_pilot/
kage_pilot_loop_logs/
kage_pilot_live_test_*.jsonl
kage_pilot_shadow_test_*.jsonl
config.json
```

## Future adaptive training

The adaptive layer remains proposed and is not enabled by default.

Potential evolution:

```text
passive telemetry
→ offline analysis
→ shadow-mode challenger
→ contextual bandit among pre-approved policies
→ explicit human promotion
```

The proper objective is safe completed rounds per unit of time, including combat, return, and recovery—not merely fast victories.

These invariants must never be learned automatically:

- KO authority;
- single trainer click;
- recovery floors;
- focus/window gates;
- key whitelist;
- F12;
- combat prohibition of `V`/`Y`;
- input release;
- water, particle, and blind-chase protections.

## Tests

Canonical workflow:

```text
.github/workflows/kage-pilot.yml
```

Minimum validation:

```powershell
python -m compileall -q pc_agent/kage_pilot
python -m py_compile kage_pilot.py kage_pilot_loop.py
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python -m unittest discover -s tests -v
python kage_pilot.py dojo --show-config
```

Tests must also cover:

- exactly one click per round;
- dialog found on each possible check;
- missing dialog without stopping the parent loop;
- F12 during every important wait;
- subprocess error and timeout;
- repeated KO rejection;
- correct KO acceptance;
- changed target/window before input;
- no stuck key after failure;
- round counters;
- fail-closed configuration.

## Validation boundary

Automated tests do not replace Windows + BYOND + the real game. Changes to capture, detection, focus, input, KO, return, or recovery must record the required physical validation.

## Definition of done

A Kage Pilot change is complete when:

- only one stable public entry point exists;
- active names do not contain version suffixes;
- safety contracts remain intact;
- relevant automated tests passed;
- real-world limitations are recorded;
- PT-BR and EN-US remain equivalent;
- personal runtime/config/log files were not versioned;
- the change exists in a traceable branch and PR;
- no “correct version” exists only in a ZIP or Desktop folder.
