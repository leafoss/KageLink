# Kage Pilot v0.3 — Target Guard

## Why

Real BYOND validation showed that `BACKGROUND_DYNAMIC` finally learned animated water, but some environmental entities could still accumulate a high `Enemy Score` and become `TARGET`, including while already in `LOST` state.

The `Target Guard` separates two questions:

```text
is this a trackable ENTITY?
        ↓
does it deserve to become a combat TARGET?
```

## Current rules

- `LOST` can never be acquired as a new TARGET;
- a recently lost current TARGET may remain above `target-keep` for about 0.8 s to tolerate short contour drop-outs;
- after that grace period, a `LOST` track falls below `target-keep`;
- `OCCLUDED` remains protected because contact with `PLAYER #000` is strong combat evidence;
- very young tracks cannot immediately become TARGET;
- inside a mature `BACKGROUND_DYNAMIC` region, a track far from the player is capped below acquire threshold unless it shows coherent combat-like approach/motion;
- minimum environmental-memory lifetime is extended to 30 s to reduce relearning the same animated water during a session.

## Next validation goal

Near water, telemetry should stop producing new targets such as:

```text
target=#NNN/LOST/.../55%+
```

During combat, a real target may still legitimately transition through:

```text
VISIBLE → OCCLUDED → brief LOST → VISIBLE
```

without `OCCLUDED` being penalized by environmental filtering.
