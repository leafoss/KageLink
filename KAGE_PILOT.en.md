# Kage Pilot — canonical documentation

[Português](KAGE_PILOT.md) · [KageLink Bible](AGENTS.en.md) · [Runtime and organization](AGENTS_RUNTIME.en.md)

This file is the **only canonical operational documentation for Kage Pilot**. Documents named `KAGE_PILOT_V0_3*` recorded development milestones and remain recoverable through Git history, but they must not be used as active instructions.

## Validated state

- Physically validated line: Dojo v0.3j with v0.3k round runtime.
- Reference merge: PR #16, commit `3c819d346d044a0c71650fcf182d3815385b7672`.
- Real validation: 10 rounds requested, 10 processed, and 10 completed, with no failures or emergency stop.
- GitHub is the only official source; ZIPs, Desktop copies, virtual environments, logs, and local configuration are not canonical sources.

## Public surface

```text
kage_pilot.py             stable general subsystem CLI
kage_pilot_dojo.py        stable Dojo training entry point
pc_agent/kage_pilot/      modular internal implementation
config/kage_pilot_dojo.json
```

New work must not create another version-suffixed public entry point. The implementation behind stable names may be replaced only after tests.

## Recommended Dojo command

From `KageLink Installer/pc_agent`:

```powershell
.\.venv-kage-pilot\Scripts\python.exe .\kage_pilot_dojo.py `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

## Protected state machine

```text
ROUND_START
→ SEARCH_TRAINER
→ CONFIRM_TRAINER
→ CLICK_TRAINER_ONCE
→ WAIT_DIALOG
→ CLICK_DIALOG_OK
→ WAIT_SPAWN
→ COMBAT_ACTIVE
→ KO_CONFIRMED
→ RETURN_TO_TRAINER
→ RECOVERY
→ ROUND_COMPLETE
```

Recoverable failures end only the current stage or round. Only a proven fatal failure or F12 stops the whole loop.

## Permanent contracts

### Single trainer click

```text
trainer_clicks_per_round <= 1
```

Dialog retries never repeat the click and never restart trainer search.

### Dialog gate

- one initial check;
- up to three additional retries;
- no repetition of the one-shot action;
- after the final failure, the round becomes `FINISHED_WITHOUT_COMBAT` and the loop may continue.

### KO identity

- the last accepted opponent is preserved across rounds;
- the same name may be rejected while the previous body is still visible;
- a rejected KO releases inputs, invalidates the target, and continues combat;
- victory requires compatible identity and current visual evidence.

### Input safety

- `R` may remain held only within the combat contract;
- arrows and `H` are short pulses;
- `V` and `Y` are tap toggles and are forbidden during combat;
- every failure, timeout, cancellation, and critical transition releases inputs;
- F12 remains the emergency stop and every wait must be interruptible.

### Recovery

Validated safety floors:

```text
HP >= 90%
Chakra >= 50%
```

A round does not complete before configured thresholds are reached.

## Code organization

“One Kage Pilot” means **one canonical surface**, not one monolithic file mixing vision, combat, post-combat, configuration, and service responsibilities.

Rules:

1. one stable public entry point per function;
2. internal modules named after responsibility rather than attempt numbers (`v03a`, `v03b`, and so on);
3. experiments are not imported by the official runtime;
4. snapshots leave the active tree once the canonical equivalent has tests;
5. Git history replaces files retained only as dead archives;
6. permanent tests describe contracts, not temporary versions.

## Configuration

Default source:

```text
config/kage_pilot_dojo.json
```

Configuration rejects unknown keys and supports CLI overrides.

## Telemetry

Logs should identify:

```text
round
state
operation
attempt
result
error_code
recoverability
elapsed
```

`completed=N` updates the public round count only in authoritative summaries:

```text
DOJO_LOOP_FINISHED
DOJO_LOOP_STOPPED
DOJO_FINAL
```

## Required tests

Preserve coverage for:

- single click;
- dialog found on each attempt and dialog absent;
- trainer occlusion and lateral reveal;
- HWND replacement and foreground loss;
- repeated KO rejected and correct KO accepted;
- subprocess nonzero/timeout;
- recovery;
- aborted round without stopping the loop;
- F12 during waits;
- no stuck keys.

## Definition of done

A change is complete only when it:

- uses the canonical surface;
- does not create another versioned file to replace the previous implementation;
- has risk-proportional tests;
- preserves F12 and cleanup;
- records when real Windows/BYOND validation is required;
- keeps equivalent PT-BR/EN-US documentation;
- does not leave the correct version only in a ZIP, log, or local folder.
