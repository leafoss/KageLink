# Kage Pilot — canonical documentation

[Português](KAGE_PILOT.md) · [KageLink Bible](AGENTS.en.md) · [3.5 Addendum](AGENTS_3_5.en.md) · [Runtime](AGENTS_RUNTIME.en.md) · [Dojo](AGENTS_DOJO.en.md)

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

KageLink 3.5.0 installs `KageLink.exe`, `KagePilotDojo.exe`, and `KagePilotRound.exe`. The helper executables are isolation and compatibility boundaries; they must route to the canonical surface and are not competing implementations.

## Organization

- one responsibility has one versionless canonical name;
- versions belong to commits, tags, releases, and changelog entries;
- do not create new `v03x`, `final2`, `new`, `hotfix`, or equivalent files;
- versioned internal modules still used by the validated engine remain temporarily as compatibility layers;
- removing those modules requires migrated imports/specs/tests, green CI, and renewed real-game validation.

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

## Trainer templates

KageLink 3.5.0 accepts independent 32×32 and 64×64 templates under:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates
```

Normal updates preserve templates. Training fails closed without a valid template. Each mode has independent data and metadata, and only a stable visual match authorizes continuation.

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

Absolute contract:

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

- F12 is the immediate global stop;
- every failure, timeout, or transition releases inputs;
- `R` is the only key normally held during combat;
- arrows and `H` are short pulses;
- `V` and `Y` are forbidden during combat;
- manual GAME control is blocked during autonomous training;
- loss of focus, HWND, PID, or visual authority reduces action;
- victory still depends on the real `has been Knocked-Out` line and current identity gates;
- recovery requires HP ≥ 90% and Chakra ≥ 50%.

## Minimum tests

```powershell
python -m py_compile kage_pilot.py kage_pilot_dojo.py kage_pilot_loop.py
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python -m unittest discover -s tests -v
python kage_pilot.py dojo --show-config
```

Also validate build and smoke checks for `KageLink.exe`, `KagePilotDojo.exe`, `KagePilotRound.exe`, Setup, and APK. Changes to capture, detection, focus, input, KO, return, or recovery require real Windows + BYOND validation before functional merge.
