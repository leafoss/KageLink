# Kage Pilot v0.3j — Facing correction during particle holds

**Date:** 2026-07-28  
**Status:** real-game validation candidate; not yet promoted to the canonical command  
**Preserved base:** v0.3i

## Observed problem

A complete round succeeded, but combat took too long because the opponent moved below the player while the character remained facing up.

The log showed that perception had already corrected its decision:

```text
FACE_UP
→ MOVE_DOWN
→ FACE_DOWN
```

However, `MotionBurstGuard` was in `MOTION_BURST_HOLD`. The previous policy blocked:

- movement;
- `H`;
- facing pulses.

Since `R` remained active, auto-attacks continued in the stale physical direction.

## v0.3j correction

During `MOTION_BURST_HOLD`, v0.3j may authorize **one facing pulse** only when all conditions below hold:

1. logical state is `MELEE`;
2. grid distance is `d <= 1`;
3. requested navigation is `FACE_UP`, `FACE_DOWN`, `FACE_LEFT` or `FACE_RIGHT`;
4. the target has current visual authority:
   - `VISIBLE`;
   - `OCCLUDED`;
   - `CONTACT_REBIND`;
5. the same target and direction are confirmed for two frames;
6. no pulse has already been sent for that target/direction combination during the current burst episode.

Expected telemetry:

```text
safety=BURST_FACE_CORRECT
face_pulse=down
held=r
move_pulse=-
H_WAIT
```

## What remains blocked

The exception does not authorize:

- pursuit;
- a movement pulse;
- `H`;
- a distant target;
- `CONTACT_MEMORY` without current visual authority;
- continuous repeated directional pulses.

These states remain absolute holds:

```text
MAP_SAVE_RESYNC
H_SETTLE_HOLD
```

`MAP_SAVE_RESYNC` still releases every key.

## Relationship with MotionBurstGuard

The guard was not removed and its thresholds were not reduced. It continues to block pursuit and skills during excessive particle motion.

The change only recognizes that, in visually confirmed adjacent melee, leaving the character facing the wrong direction for dozens of seconds is less safe and less useful than sending one cardinal pulse already used by the normal facing controller.

## Files

```text
kage_pilot_live_v03j_round.py
kage_pilot_loop_v03j.py
tests/test_kage_pilot_v03j_burst_facing.py
```

## Required validation

Before promoting v0.3j to `kage_pilot_dojo.py`:

- [ ] targeted tests finish with `OK`;
- [ ] full suite finishes with `OK`;
- [ ] one real round reports `BURST_FACE_CORRECT` when direction changes during particles;
- [ ] the character physically faces the opponent;
- [ ] the new state never authorizes pursuit movement;
- [ ] the new state never fires `H`;
- [ ] `MAP_SAVE_RESYNC` still reports `held=-`;
- [ ] the loop finishes with `ROUND 1: COMPLETE`;
- [ ] canonical promotion happens only after real-game validation.

## Release decision

v0.3i remains the validated baseline. v0.3j is an additive isolated correction. After in-game approval, the public entry point may be updated to use v0.3j and the release-candidate documentation will be revised.
