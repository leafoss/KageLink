# Kage Pilot v0.3 — Target Guard v2

## Why

Real validation showed that `BACKGROUND_DYNAMIC` now learns animated water and substantially reduces false positives, but some environmental entities could still accumulate a high `Enemy Score` and receive `TARGET LOCK`.

The correction explicitly separates three concepts:

```text
motion -> ENTITY -> eligible TARGET
```

`Enemy Score` remains diagnostic. It is no longer sufficient by itself to create a combat lock.

## Default PLAYER position

The default `PLAYER #000` position now uses the latest calibration validated during real combat:

```text
player-x = 0.5181
player-y = 0.4706
PLAYER box = 18x38 px
```

Left-click calibration remains available for manual refinement.

## TARGET rules

- `LOST`: remains in tracker/reacquisition memory but is never an active TARGET;
- `OCCLUDED`: remains eligible because it represents known contact at the PLAYER boundary;
- nearby `VISIBLE`: may become eligible after minimum persistence;
- distant `VISIBLE`: must show coherent approach, residual speed, and temporal memory;
- mature `BACKGROUND_DYNAMIC` region + distant entity: blocks TARGET acquisition regardless of `Enemy Score`;
- very young entities cannot instantly acquire TARGET.

Initial defaults:

```text
target minimum age          = 0.70 s
target minimum observations = 4
near target distance        = 145 px
far approach maximum        = 280 px
dynamic-region block        = 0.42
```

## Conceptual safety

v0.3 remains read-only. No key is sent to the game.

The core rule is now:

```text
MOTION != ENTITY
ENTITY != ENEMY
ENEMY != TARGET
```

The future controller should consume only `TARGET`, never raw candidates or every entity with a high score.
