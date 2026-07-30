# Kage Pilot

[Português](KAGE_PILOT.md) · [KageLink Bible](AGENTS.en.md) · [Normative Dojo contract](AGENTS_DOJO.en.md)

**Kage Pilot** is the local perception, control, and training subsystem for the **Shinobi Story Online** Dojo. Since KageLink 3.5.0, it is part of the Windows distribution and can be controlled from the Desktop or the authenticated Android app.

This is the only active Kage Pilot technical document in EN-US. Older records carrying version names, hotfix letters, or dates remain preserved in Git history and in the Pull Requests that validated them.

## Canonical state

- **Product version:** KageLink 3.5.0.
- **Development command surface:** `KageLink Installer/pc_agent/kage_pilot.py`.
- **Dojo command:** `python kage_pilot.py dojo`.
- **Configuration:** `KageLink Installer/pc_agent/config/kage_pilot_dojo.json`.
- **Public service:** `pc_agent.kage_pilot.DojoTrainingService`.
- **Workflow:** `.github/workflows/kage-pilot.yml`.
- **Installed executables:** `KageLink.exe`, `KagePilotDojo.exe`, and `KagePilotRound.exe`.
- **User templates:** `%LOCALAPPDATA%\KageLink\data\kage_pilot\templates`.

The recorded physical baseline completed ten rounds:

```text
DOJO_LOOP_FINISHED requested=10 processed=10 completed=10
finished_without_combat=0 failed=0 emergency_stopped=0
```

## Organization rule

There is one human-facing public surface:

```text
kage_pilot.py
```

It owns these commands:

```text
dojo
record
mark
train
train-v2
pilot
pilot-v2
capture-template
init-config
dojo-v2
```

Internal code remains modular by responsibility. Versions belong in commits, tags, releases, and changelogs; new work must not create another entry point named `v03l`, `final2`, `new`, or `hotfix`.

The physically validated internal chain still contains historical compatibility layers. They are not public surfaces and may only be extracted into canonical names through a dedicated change with full CI and renewed real-game validation.

## Installed architecture

```text
Desktop or Android app
       ↓ authenticated API
KageLink.exe
       ↓ DojoTrainingService
KagePilotDojo.exe
       ↓ one isolated round at a time
KagePilotRound.exe
       ↓
Shinobi Story Online
```

- The engine runs only on the Windows computer that owns the game.
- Android never runs vision, keyboard, or combat logic.
- Desktop and Android control the same public state.
- Windows blocks concurrent GAME commands while training is active.
- The installation does not depend on external Python or loose scripts.

## Development execution

From `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py dojo
```

Ten rounds:

```powershell
python kage_pilot.py dojo `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

Show the effective configuration:

```powershell
python kage_pilot.py dojo --show-config
```

`--rounds 0` runs continuously until an explicit stop or F12.

## 32×32 and 64×64 templates

The installation does not use a bundled Dojo Trainer image as its primary authority. The user registers independent crops for the real game modes:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates\
├── dojo_trainer_32.png
├── dojo_trainer_64.png
└── templates.json
```

Rules:

- each mode is persisted and removed independently;
- normal upgrades preserve the files;
- the UI accepts PNG, JPEG, WebP, and BMP and normalizes them;
- both templates may be loaded at the same time;
- the detector selects only one stable match;
- strong ambiguity fails closed;
- the installed runtime cannot start without at least one valid template;
- source-tree calibration is development compatibility only.

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

A recoverable failure ends only the attempt or round. F12 performs `EMERGENCY_STOP`, releases inputs, and ends the loop.

## Absolute Trainer contract

```text
trainer_clicks_per_round <= 1
```

After `TRAINER_CLICK_ONCE`, dialog retries may not:

- click the Trainer again;
- search for another Trainer to repeat the request;
- move the character to restart the interaction;
- start a second spar request.

Default flow:

```text
1 Trainer click
→ initial wait
→ check 1
→ retry wait + check 2
→ retry wait + check 3
→ retry wait + check 4
```

Four failures end only that round as `FINISHED_WITHOUT_COMBAT`. The round consumes its number and the loop continues when safe.

## Visual acquisition

Vision creates candidates; it does not authorize input by itself. Acquisition requires current and stable confirmation. A short lateral reveal probe may be used when the player may be hiding the Trainer.

Old position memory never authorizes a click, `V`, or recovery without current visual evidence.

## Combat

Permanent contracts:

- `R` is the only key normally held;
- arrows and `H` are short pulses;
- `V` and `Y` are tap toggles and are forbidden during combat;
- loss of target, focus, or visual authority reduces action;
- `MAP_SAVE_RESYNC` and `H_SETTLE_HOLD` are absolute holds;
- particle-facing correction requires a current, adjacent, confirmed target;
- error, timeout, stop, and shutdown release every input.

## KO authority

The real phrase remains the combat-completion authority:

```text
has been Knocked-Out
```

The last accepted opponent name is carried into the next round. A repeated KO from the previous opponent is rejected, the target is invalidated, and combat continues. Victory is accepted only for a different opponent with sufficient current visual evidence.

## Return and recovery

Protected floors:

```text
HP >= 90%
Chakra >= 50%
```

- `V` requires current visual confirmation of the Trainer.
- `Y` may remain enabled only during meditation and must be disabled after the threshold is reached.
- recovery timeout must not be reported as success.

## Counters

```text
requested
processed
completed
finished_without_combat
failed
emergency_stopped
```

`--rounds 10` processes rounds numbered 1 through 10. It must not silently create round 11 as compensation.

## Authenticated API

```text
GET    /api/dojo/status
POST   /api/dojo/start
POST   /api/dojo/stop
GET    /api/dojo/templates
GET    /api/dojo/templates/{mode}/image
POST   /api/dojo/templates/{mode}
DELETE /api/dojo/templates/{mode}
```

Every endpoint uses the KageLink Bearer Token. Starting without an available runtime or a valid template must fail closed. Stop must release inputs even when the process already ended.

## GAME interlock

While `running=true`:

- manual GAME activation is rejected;
- manual GAME key state is rejected;
- remote center click is rejected;
- template replacement or deletion is blocked;
- chat and STATUS remain independent;
- F12 remains the local emergency stop.

## Local data

Do not version:

```text
.venv-kage-pilot/
data/kage_pilot/
kage_pilot_loop_logs/
kage_pilot_*.jsonl
config.json
```

Templates, calibration, frames, and logs belong to the user installation.

## Future adaptive training

Acceptable progression:

```text
passive telemetry
→ offline analysis
→ shadow-mode challenger
→ pre-approved policy
→ explicit human promotion
```

The following may never be learned automatically:

- KO authority;
- single Trainer click;
- recovery floors;
- target/focus gates;
- key whitelist;
- F12;
- input release;
- the ban on `V` and `Y` during combat;
- particle, water, and blind-chase protections.

## Validation

Main CI commands:

```powershell
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python -m unittest discover -s tests -v
python -m compileall .
python kage_pilot.py dojo --show-config
```

Distribution must also validate:

- all three executable builds;
- `--help` for both helpers;
- Desktop smoke launch;
- Setup containing all three executables;
- template upload, persistence, and removal;
- Flutter localization, analyze, and tests;
- release APK;
- one installed real round in applicable modes;
- Desktop/Android start, stop, and status;
- GAME interlock;
- F12 and input release.

Automated tests do not replace real Windows + BYOND validation.
