# Kage Pilot v0.1

[Português](KAGE_PILOT.md)

**Kage Pilot** is an experimental local KageLink subsystem that learns combat actions demonstrated by the player and reproduces them inside the `Shinobi Story Online` Dojo.

> v0.1 status: functional recording → dataset → training → Pilot → Dojo loop pipeline. The first learner is deliberately simple and should be refined with real Dojo data.

## Architecture

```text
KAGE PILOT v0.1
│
├── Recorder
│   ├── existing KageLink HWND capture
│   ├── physical keyboard
│   ├── mouse
│   └── timestamp
│
├── Dataset
│   ├── JPEG frames
│   ├── action snapshots
│   ├── action runs + duration
│   └── victory / defeat
│
├── Combat Learner
│   └── visual-prototype behavioral clone
│
├── Pilot
│   └── predicts and applies keyboard state
│
└── Dojo Manager
    ├── start sequence
    ├── Pilot during combat
    ├── visual victory/defeat detector
    ├── rest sequence
    └── repeat
```

The Dojo Manager is deterministic. AI owns only the part that should be learned: **combat**.

## Safety and isolation

- Pilot reuses KageLink's game-window-specific `Shinobi Story Online` capture.
- Control reuses `GameInputController`, including window focus and stuck-key protection.
- Automated clicks use normalized coordinates inside the game window.
- Pilot cannot execute generic system commands or programs.
- No Interpreter, chat, RAW, Memory Reviewer, Android, or current protocol changes are required.

## 1. Record demonstrations

From `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py record
```

While recording:

```text
F11 = finish the fight as victory
F12 = finish the fight as defeat
F10 = stop Recorder
```

After F11/F12, a new session starts automatically so several fights can be demonstrated in one run.

Default data location:

```text
%LOCALAPPDATA%\KageLink PC Agent\data\kage_pilot\sessions\
```

Each fight contains:

```text
<session>/
├── manifest.json
├── samples.jsonl
├── actions.jsonl
└── frames/
    ├── 000000.jpg
    ├── 000001.jpg
    └── ...
```

`samples.jsonl` stores keyboard/mouse state with its frame and timestamp. `actions.jsonl` consolidates consecutive states and stores `duration_ms`.

## 2. Train the first Combat Learner

```powershell
python kage_pilot.py train --model kage_pilot_model.json
```

By default only `victory` sessions train the model so losing demonstrations are not treated as desired behavior.

Experimental inclusion of defeats:

```powershell
python kage_pilot.py train --model kage_pilot_model.json --include-defeats
```

v0.1 learns **keyboard states** from a compact visual representation of the frame. Mouse input is recorded in the dataset but is not yet part of the learned combat policy.

## 3. Test combat only

```powershell
python kage_pilot.py pilot --model kage_pilot_model.json --seconds 60
```

Pilot captures the game, predicts an action, and passes only predicted keys to KageLink's safe game controller.

## 4. Calibrate Dojo Manager

Create a configuration first:

```powershell
python kage_pilot.py init-config --output dojo_config.json
```

It contains:

- `start_sequence`: clicks/keys used to talk to the NPC and start;
- `rest_sequence`: actions used after combat;
- `victory`: required visual template;
- `defeat`: optional visual template;
- `rested`: optional recovered-state template;
- safety delays and timeouts.

### Capture a template

With the desired state visible:

```powershell
python kage_pilot.py capture-template --output templates/victory.png --region 0.35 0.15 0.30 0.15
```

The region is normalized:

```text
X Y WIDTH HEIGHT
0.0 ───────────── 1.0
```

Choose a small stable region that clearly identifies victory, defeat, or a recovered character.

**Do not use the example coordinates without calibrating them in your Dojo.** They are safe placeholders only.

## 5. Run the complete loop

```powershell
python kage_pilot.py dojo --model kage_pilot_model.json --config dojo_config.json --cycles 10
```

Flow:

```text
start training
    ↓
wait for arena
    ↓
Pilot fights
    ↓
victory detected
    ↓
release every key
    ↓
rest
    ↓
recovered / wait completed
    ↓
next fight
```

If combat exceeds `combat_timeout_seconds`, Manager releases all keys and returns `timeout` rather than running indefinitely.

## v0.1 tests

Automated tests cover:

1. session creation/finalization;
2. frames, keyboard, mouse, and timestamps;
3. action runs and duration generation;
4. training and model persistence;
5. distinct action prediction from synthetic images;
6. visual template detection;
7. a simulated `start → Pilot → victory → rest` cycle.

Command:

```powershell
python -m unittest tests.test_kage_pilot -v
```

## Validation boundary

Automated tests validate the software and control loop but cannot replace BYOND validation. The automated development environment does not contain Windows + `Shinobi Story Online`, so real HWND capture, `SendInput`, and Dojo templates require a short calibration run on your PC before Pilot is considered game-validated.

This separation is intentional: v0.1 does not invent sprites, coordinates, or screens that have not been observed yet.
