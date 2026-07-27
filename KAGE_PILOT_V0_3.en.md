# Kage Pilot v0.3 — Entity Observer

## Goal

v0.3 temporarily stops trying to control combat directly from the whole frame. Before controlling Leafos, the system must build an explicit representation of the world:

```text
HWND capture
    ↓
local contrast (CLAHE)
    ↓
contours and motion
    ↓
Lucas–Kanade optical flow
    ↓
global camera-motion compensation
    ↓
Entity Tracker
    ↓
temporal memory
    ↓
Enemy Score
```

This first milestone is **observation only**. No key is sent to the game.

## What the window shows

- `PLAYER #000`: initial player anchor, configurable by normalized coordinates or direct click in the preview.
- `ENTITY #NNN`: persistent candidates found from motion and contours.
- temporal trail for each entity;
- residual velocity after global scene-motion compensation;
- direction;
- observed time;
- approach relative to the player;
- distance to the player;
- hostility memory;
- `ENEMY SCORE` from 0% to 100%;
- motion mask used to create candidates.

## Initial Enemy Score

The score is still heuristic. It combines:

- temporal persistence;
- motion independent from the background;
- approach toward the player;
- motion heading relative to the player;
- plausible distance;
- candidate shape and size;
- accumulated hostile-behavior memory.

This score is not a final truth. It exists to make decisions visible and tunable before adding a trained visual model.

## Installation

From `KageLink Installer/pc_agent`:

```powershell
.\.venv-kage-pilot\Scripts\python.exe -m pip install -r requirements.txt
```

v0.3 adds OpenCV and NumPy to the PC Agent environment.

## Run

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py
```

Observer-window controls:

```text
left click Leafos = recalibrate PLAYER #000
Q or ESC = exit
```

The Observer does not send these actions to Shinobi Story Online; they are read only by the OpenCV preview window.

## Initial player calibration

The first real validation showed that the old `0.50 / 0.55` anchor sat below Leafos and allowed the player sprite itself to become an `ENTITY`. The runtime defaults are now approximately:

```text
player-x = 0.51
player-y = 0.48
player-radius = 26
```

Visual calibration is now the recommended method:

1. run the Observer;
2. left-click directly on Leafos;
3. `PLAYER #000` moves immediately;
4. tracking state is reset so any false player entity created from the old anchor is removed;
5. PowerShell prints the matching `--player-x` and `--player-y` values.

Manual reuse example:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py `
  --player-x 0.5100 `
  --player-y 0.4800 `
  --player-radius 26
```

The `PLAYER #000` circle is an exclusion zone; it does not need to trace the sprite exactly. It should cover Leafos without blocking too much nearby space. Already-tracked entities may enter this zone during melee without losing their `ENTITY ID`.

## Validation gate

v0.3a is considered validated when, during a real fight:

1. the same opponent keeps the same `ENTITY ID` for several seconds;
2. the tracker does not classify the whole background as enemies when the camera moves;
3. `approaches player` changes to `YES` when the opponent advances;
4. distance to the player increases after knockback;
5. the real opponent's `Enemy Score` exceeds objects and temporary effects;
6. the box and trail continue following the target.

## Next milestone

Only after the Observer is validated will the v0.3b controller be added:

```text
SEARCH → APPROACH → MELEE → DISPLACED → RECOVER → POST_COMBAT
```

`LEFT`, `RIGHT`, `R +REP`, and `H` decisions will be based on target spatial state rather than whole-frame visual similarity.
