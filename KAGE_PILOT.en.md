# Kage Pilot — canonical documentation

[Português](KAGE_PILOT.md) · [KageLink Bible](AGENTS.en.md) · [Runtime](AGENTS_RUNTIME.en.md) · [Dojo](AGENTS_DOJO.en.md)

**Kage Pilot** is the KageLink 3.5.0 subsystem responsible for visual perception, safe control, and repeated Dojo training in **Shinobi Story Online**.

This is the only active Kage Pilot document in EN-US. Documents named after versions, dates, hotfixes, or milestones belong to Git history and must not compete as operational documentation.

## Canonical surface

```text
Public source: KageLink Installer/pc_agent/kage_pilot.py
Dojo command: python kage_pilot.py dojo
Public loop: KageLink Installer/pc_agent/kage_pilot_loop.py
Configuration: KageLink Installer/pc_agent/config/kage_pilot_dojo.json
Service: pc_agent.kage_pilot.DojoTrainingService
```

KageLink 3.5.0 installs:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

The helper executables are isolation and compatibility boundaries. They are not competing implementations and must route to the canonical surface.

## Code organization

- One responsibility has one versionless canonical name.
- Versions belong to commits, tags, releases, and changelog entries.
- Do not create new `v03x`, `final2`, `new`, `hotfix`, or equivalent filenames.
- Historical internal modules still used by the validated engine remain temporarily as compatibility layers.
- Removing them requires semantic extraction, a green suite, and renewed real-game validation.

## Run

From `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py dojo `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

Show effective configuration:

```powershell
python kage_pilot.py dojo --show-config
```

## Trainer templates in 3.5.0

KageLink accepts independent templates for 32×32 and 64×64 modes. They belong to the user's installation and remain outside `Program Files`:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates
```

Rules:

- normal updates preserve templates;
- training fails closed without a valid template;
- each mode has independent data and metadata;
- detection chooses only a stable visual match;
- old templates, stale coordinates, or isolated memory never authorize a click.

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

### Single click

```text
trainer_clicks_per_round <= 1
```

After `TRAINER_CLICK_ONCE`, dialog retries must never search for, move toward, or click the Trainer again.

Default flow:

```text
1 click
→ 1 initial wait/check
→ up to 3 additional waits/checks
→ final failure ends only the round
```

A round without a dialog consumes its number and does not create a silent compensation round.

## Safety

- F12 is the immediate global stop.
- Every failure, timeout, or transition releases inputs.
- `R` is the only key normally held during combat.
- arrows and `H` are short pulses.
- `V` and `Y` are forbidden during combat.
- manual GAME input is blocked while autonomous training is active.
- loss of focus, HWND, PID, or visual authority reduces action and never increases aggression.
- victory authority remains the real `has been Knocked-Out` chat line with current identity gates.
- recovery cannot be declared before HP ≥ 90% and Chakra ≥ 50%.

## Results

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

`NOT_FOUND`, `TIMEOUT`, or `FAILED` are not automatically fatal. Each stage must state whether it ends an attempt, round, module, or process.

## Minimum validation

```powershell
python -m py_compile kage_pilot.py kage_pilot_dojo.py kage_pilot_loop.py
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python -m unittest discover -s tests -v
python kage_pilot.py dojo --show-config
```

Also validate build and smoke checks for `KageLink.exe`, `KagePilotDojo.exe`, `KagePilotRound.exe`, Setup, and APK.

Changes to capture, detection, focus, input, KO, return, or recovery require real Windows + BYOND validation before functional merge.

## Definition of done

- one canonical public surface;
- external compatibility preserved;
- no new active versioned filenames;
- safety contracts preserved;
- tests and limitations reported honestly;
- equivalent PT-BR and EN-US coverage;
- personal files and templates remain outside Git;
- traceable branch and PR;
- no correct version exists only in a ZIP or Desktop folder.
