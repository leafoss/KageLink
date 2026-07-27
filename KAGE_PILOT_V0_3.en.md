# Kage Pilot v0.3 — Entity Observer

## Goal

v0.3 temporarily stops trying to control combat directly from the whole frame. Before controlling Leafos, the system must build an explicit world representation:

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
BACKGROUND_DYNAMIC memory
    ↓
Entity Tracker + appearance
    ↓
temporal memory / occlusion / relative side
    ↓
Enemy Score
    ↓
TARGET LOCK
```

This milestone remains **observation only**. No key is sent to the game.

## What the window shows

- `PLAYER #000`: calibratable player anchor;
- tight vertical player box;
- `ENTITY #NNN`: persistent candidates;
- temporal trail;
- residual velocity after camera compensation;
- direction and relative side (`LEFT/RIGHT/UP/DOWN`);
- `VISIBLE`, `LOST`, or `OCCLUDED` state;
- visual similarity used for association;
- observed time, distance, and approach;
- hostility memory and `ENEMY SCORE`;
- `TARGET LOCK`;
- number of candidates suppressed by `BACKGROUND_DYNAMIC`;
- dormant identities waiting for reacquisition.

## PLAYER box

The old circle has been replaced by a vertical rectangle that more closely matches the real sprite volume.

```text
player-box-width  = 18 px
player-box-height = 38 px
```

The box prevents a new entity from spawning on top of Leafos. An already-known entity may reach the player, but its logical box cannot pass through the `PLAYER #000` core.

The center remains calibratable by left-clicking directly on Leafos. Recalibration resets the tracker and TARGET LOCK while preserving already-learned environmental memory.

## BACKGROUND_DYNAMIC

Animated water and similar scenery can create many motion contours even though they are not entities. Real validation showed that water contours may be spread across a wide band, so the current filter no longer requires three candidates to be close together in the same frame.

Environmental memory uses **temporal recurrence by region**:

```text
motion returns to the same cell
        ↓
accumulate hits over time
        ↓
cell matures
        ↓
BACKGROUND_DYNAMIC
```

Appearance remains supporting evidence but is no longer mandatory for clearly scenery-like contours. Vertical character-shaped candidates require stronger regional and visual evidence before suppression.

Initial defaults:

```text
background cell size       = 32 px
minimum frame activity     = 3 remote candidates
minimum temporal hits      = 8
minimum age                = 0.8 s
appearance similarity      = 0.88
memory TTL                 = 12 s
```

The panel shows:

```text
dynamic bg suppressed: N
dynamic bg cells: N
```

The combat tracker protects candidates close to the player, in `OCCLUDED`, or moving toward the player with a coherent trajectory. Existing tracks inside a strongly dynamic region may also be retroactively removed as `BACKGROUND_DYNAMIC`.

## Appearance memory

Each candidate receives a lightweight visual signature built from:

- intensity histogram;
- coarse quadrant structure;
- edge density.

This is not a neural model. It is a low-cost visual memory used to:

- reduce ID swaps between nearby candidates;
- recognize similar environmental patterns;
- help recover the same `ENTITY ID` after temporary visual loss.

Appearance is combined with predicted position, size, and shape in the matching cost.

## Stable Entity Tracker

The tracker uses:

1. global camera motion from Lucas–Kanade;
2. entity residual velocity;
3. predicted position;
4. bounding-box size/shape;
5. appearance similarity;
6. relative side to the player.

Main parameters:

```text
track-match-distance = 105 px
track-ttl            = 2.0 s
```

During short drop-outs, velocity decays gradually instead of being reset immediately.

## OCCLUDED / player contact

When an observed bounding box tries to cross the player box, the system does not assume the enemy has become part of the PLAYER.

Flow:

```text
known ENTITY approaches
    ↓
remember LEFT / RIGHT / UP / DOWN
    ↓
contour enters PLAYER box
    ↓
state = OCCLUDED
    ↓
logical box is held at PLAYER boundary
    ↓
ID + side + clean appearance are preserved
    ↓
visual separation
    ↓
reacquire the same ID
```

While `OCCLUDED`, the mixed PLAYER+enemy contour does not replace the clean appearance memory.

## Relative-side memory

Each entity stores its last reliable side:

```text
LEFT
RIGHT
UP
DOWN
```

This memory survives occlusion and will later feed the v0.3b controller when deciding recovery direction without relying only on the current frame.

## DORMANT / reacquisition

After exceeding the active TTL, an established identity is not forgotten immediately. It enters a dormant memory for a few seconds.

Defaults:

```text
reacquire TTL        = 5.0 s
reacquire distance   = 180 px
reacquire similarity = 0.82
```

When a compatible candidate reappears, the same `ENTITY ID` is restored instead of creating a new number.

## TARGET LOCK hysteresis

```text
target-acquire = 55%
target-keep    = 38%
```

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
score < 38% or identity truly expires
  ↓
release lock
```

## Initial Enemy Score

The score remains heuristic and combines persistence, independent motion, approach, heading, distance, shape, and hostility memory. It is still a diagnostic signal rather than final truth.

## Installation

From `KageLink Installer/pc_agent`:

```powershell
.\.venv-kage-pilot\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py
```

Useful additional parameters:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py `
  --background-similarity 0.88 `
  --background-min-hits 8 `
  --background-min-age 0.8 `
  --reacquire-ttl 5 `
  --reacquire-distance 180 `
  --reacquire-similarity 0.82 `
  --telemetry-seconds 2
```

To compare with environmental filtering disabled:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py --no-dynamic-background
```

Controls:

```text
left-click Leafos = recalibrate PLAYER
Q or ESC          = exit
```

## Telemetry

By default the Observer prints one line every 2 seconds:

```text
OBS t= 12.0s entities=15 bg_mature=8 bg_strong=3 suppressed=6 pruned=2 dormant=1 target=#042/VISIBLE/RIGHT/67.0%
```

This makes it possible to evaluate dynamic-background learning and TARGET evolution over time instead of relying on a single screenshot.

## Validation gate

v0.3a is considered validated when:

1. `PLAYER #000` tightly covers the sprite;
2. the player itself does not spawn as an `ENTITY`;
3. water/repetitive effects are progressively suppressed;
4. the same opponent keeps the same ID for several seconds;
5. `TARGET LOCK` survives small score fluctuations;
6. player contact produces `OCCLUDED` without the box crossing PLAYER;
7. relative side remains stable through occlusion;
8. the same ID can be recovered after a short separation;
9. camera motion does not become an avalanche of enemies.

## Next milestone

Only after this perception layer is validated will the v0.3b controller be added:

```text
SEARCH → APPROACH → MELEE → DISPLACED → RECOVER → POST_COMBAT
```

`LEFT`, `RIGHT`, `R +REP`, and `H` will be decided from the target's spatial and temporal state, not whole-frame similarity.
