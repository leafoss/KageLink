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

- `PLAYER #000`: initial camera-relative player anchor, configurable by normalized coordinates.
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

Observer-window keys:

```text
Q or ESC = exit
```

The Observer does not send these keys to Shinobi Story Online; they are read only by the OpenCV preview window.

## Initial player calibration

The first version uses a camera-relative anchor for the player. Defaults:

```text
player-x = 0.50
player-y = 0.55
player-radius = 26
```

Example:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py `
  --player-x 0.48 `
  --player-y 0.58 `
  --player-radius 30
```

The `PLAYER #000` circle should cover Leafos without including the opponent. This exclusion prevents the player from being created as a hostile entity.

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
