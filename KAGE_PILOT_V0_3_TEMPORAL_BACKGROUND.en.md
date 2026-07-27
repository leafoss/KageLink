# Kage Pilot v0.3 — Temporal-Recurrence Dynamic Background

## Why this revision exists

Real BYOND validation showed that animated water could produce many `ENTITY` tracks while the previous filter stayed at `dynamic bg cells: 0` even after more than 10,000 frames. The cause was the same-frame local-density requirement: water contours were spread across a wide band and did not necessarily have three neighbors within 58 px.

## New rule

Environmental memory now learns **temporal recurrence by region**.

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

The combat tracker still protects candidates that are close to the player, `OCCLUDED`, or moving toward the player with a coherent trajectory.

## Telemetry

By default the Observer prints one line every 2 seconds:

```text
OBS t=  12.0s entities= 15 bg_mature= 8 bg_strong= 3 suppressed= 6 pruned= 2 dormant= 1 target=#042/VISIBLE/RIGHT/67.0%
```

Fields:

- `entities`: active tracks;
- `bg_mature`: mature dynamic-background cells;
- `bg_strong`: cells with strong environmental evidence;
- `suppressed`: candidates discarded before becoming tracks;
- `pruned`: existing tracks retroactively removed as background;
- `dormant`: identities waiting for reacquisition;
- `target`: current target ID, state, relative side, and Enemy Score.

Change the interval with `--telemetry-seconds`. Use `--telemetry-seconds 0` to disable it.

## PLAYER recalibration

Clicking Leafos again resets entities and TARGET LOCK while preserving learned environmental memory.

## Validation gate

During a stationary test near water, `bg_mature` should stop remaining at zero, `suppressed`/`pruned` should begin increasing, and `entities` should fall as the region is learned. During combat, the real opponent should remain protected by temporal coherence and its spatial relationship to the player.
