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
    ↓
TARGET LOCK
```

This first milestone is **observation only**. No key is sent to the game.

## What the window shows

- `PLAYER #000`: calibratable player anchor;
- tight vertical player box instead of the old circular exclusion zone;
- `ENTITY #NNN`: persistent candidates found from motion and contours;
- temporal trail for each entity;
- residual velocity after global scene-motion compensation;
- direction;
- observed time;
- approach relative to the player;
- distance to the player;
- hostility memory;
- `ENEMY SCORE` from 0% to 100%;
- `TARGET LOCK` state;
- motion mask used to create candidates.

## PLAYER box

The initial circle has been replaced by a vertical rectangle that more closely matches the volume occupied by the real sprite and protects less empty space.

Current defaults:

```text
player-box-width  = 18 px
player-box-height = 38 px
```

The box is a **spawn exclusion zone for new entities**. It prevents Leafos from becoming an `ENTITY`, but it does not erase an already-known opponent when that enemy enters melee range or overlaps the player.

The center can be calibrated by left-clicking directly on Leafos in the Observer window. Calibration resets temporal tracking memory to remove false tracks created by the previous position.

## Stable Entity Tracker

The v0.3 tracker now uses four signals to preserve identity:

1. global camera motion estimated with Lucas–Kanade;
2. the entity's recent residual velocity;
3. distance from the predicted position;
4. bounding-box size/shape consistency.

Expected position uses both camera motion and recent residual entity velocity. This helps recover the same ID when a contour disappears for a few frames or the target moves rapidly.

Real-test defaults:

```text
track-match-distance = 105 px
track-ttl            = 2.0 s
```

During short drop-outs, part of the previous velocity is retained and decays gradually instead of being reset immediately.

## TARGET LOCK hysteresis

Acquiring a target and keeping a target are different operations.

Defaults:

```text
target-acquire = 55%
target-keep    = 38%
```

Flow:

```text
no target
  ↓
ENTITY >= 55%
  ↓
TARGET LOCK
  ↓
score may fluctuate between 38% and 55%
  ↓
keep TARGET
  ↓
score < 38% or entity expires
  ↓
release lock
```

This prevents target loss or switching because of small one-frame score fluctuations.

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

v0.3 uses OpenCV and NumPy in the PC Agent environment.

## Run

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py
```

Optional parameters:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py `
  --player-box-width 18 `
  --player-box-height 38 `
  --match-distance 105 `
  --track-ttl 2.0 `
  --target-acquire 55 `
  --target-keep 38
```

Observer-window controls:

```text
left-click Leafos = recalibrate PLAYER
Q or ESC          = exit
```

The Observer does not send these actions to Shinobi Story Online; they are read only by the OpenCV preview window.

## Validation gate

v0.3a is considered validated when, during a real fight:

1. `PLAYER #000` tightly covers the sprite with a vertical box;
2. the player itself does not spawn as an `ENTITY`;
3. the same opponent keeps the same `ENTITY ID` for several seconds;
4. the tracker does not classify the whole background as enemies when the camera moves;
5. `approaches player` changes to `YES` when the opponent advances;
6. distance to the player increases after knockback;
7. the real opponent's `Enemy Score` exceeds objects and temporary effects;
8. once acquired, `TARGET LOCK` survives small score fluctuations;
9. the box and trail continue following the target.

## Next milestone

Only after the Observer is validated will the v0.3b controller be added:

```text
SEARCH → APPROACH → MELEE → DISPLACED → RECOVER → POST_COMBAT
```

`LEFT`, `RIGHT`, `R +REP`, and `H` decisions will be based on target spatial state rather than whole-frame visual similarity.
