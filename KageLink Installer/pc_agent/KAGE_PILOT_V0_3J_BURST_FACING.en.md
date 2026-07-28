# Kage Pilot v0.3j — Facing correction during particle holds

**Date:** 2026-07-28  
**Status:** validated in a real round and promoted to the canonical command  
**Current baseline:** v0.3j

## Observed problem

An earlier complete round succeeded, but combat took too long because the opponent moved below the player while the character remained facing up.

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

Exception telemetry, when needed:

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
- continuously repeated directional pulses.

These states remain absolute holds:

```text
MAP_SAVE_RESYNC
H_SETTLE_HOLD
```

`MAP_SAVE_RESYNC` still releases every key.

## Relationship with MotionBurstGuard

The guard was not removed and its thresholds were not reduced. It continues to block pursuit and skills during excessive particle motion.

The change only recognizes that, in visually confirmed adjacent melee, leaving the character physically faced away from the opponent for dozens of seconds is less safe and less useful than sending one cardinal pulse already used by the normal facing controller.

## Validation performed

The later real v0.3j round confirmed:

- combat rated excellent by the user;
- stable facing and attacking;
- no pursuit movement enabled by the new state;
- no `H` authority granted by the facing exception;
- exactly one trainer click;
- chat-authoritative KO;
- return to the trainer;
- correct `Y` on/off recovery behavior;
- `ROUND 1: COMPLETE`.

The sampled printed telemetry did not necessarily contain a `BURST_FACE_CORRECT` line because the scenario may have been resolved by normal facing pulses between hold periods. The narrow exception remains covered by targeted tests.

## Files

```text
kage_pilot_live_v03j_round.py
kage_pilot_loop_v03j.py
tests/test_kage_pilot_v03j_burst_facing.py
```

## Release state

v0.3j has been promoted to:

```text
kage_pilot_dojo.py
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
```

The full Windows suite, three consecutive canonical-command rounds and Rafael's explicit approval are still required before merge.
