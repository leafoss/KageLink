# Kage Pilot v0.3 — Live Control Gate 1 (EN-US)

## Goal

Validate real combat with the smallest possible automated action set after the Entity Observer and Shadow Combat stages.

At this stage Kage Pilot sends real keys, but only:

- `R` as the combat base state, using the already validated BYOND repeat pattern;
- short arrow pulses for approach/recovery;
- short direction pulses to correct facing in melee.

`H` remains Shadow Mode only. The console may print `H_READY(SHADOW)`, but no H key is sent.

## Dead-man movement rule

Arrow keys are no longer persistent held state. Every iteration explicitly returns to base `R` before any directional command.

For example, `MOVE_RIGHT` is executed as:

```text
R
↓
R + RIGHT for ~90 ms
↓
R again
```

A bad decision therefore cannot leave an arrow permanently held. Continuing movement requires fresh authorization on later perception cycles.

## Pursuit confirmation and watchdog

- a distant target/direction must appear in at least 2 consecutive decisions before the first movement pulse;
- a distant `ENTITY ID` switch resets that confirmation;
- if grid distance does not improve for roughly 1.15 s, pursuit is stopped (`NO_PROGRESS_HOLD`);
- a short cooldown follows before pursuit may restart.

This limits how far Leafos can travel behind a persistent false target.

## Impact/particle guard

Strong attacks may generate wind/particles that create many moving regions at once. `MotionBurstGuard` maintains a recent baseline for:

- active GRID cells;
- entity/contour population.

A sudden spike well above baseline produces:

```text
MOTION_BURST_HOLD
→ R remains active
→ no arrow movement
→ no facing pulse
→ wait for scene settling (~0.75 s)
```

The spike is not immediately learned into the baseline, preventing one visual explosion from becoming the new definition of normal motion.

## Target rules

- `d <= 1 cell`: MELEE. Keep R and only correct facing with a short pulse when necessary.
- `d >= 2 cells`: APPROACH/RECOVER only with current visual confirmation (`VISIBLE`/`OCCLUDED`).
- TARGET temporarily unavailable: keep R but do not move blindly.
- `CONTACT_MEMORY` preserves identity/facing only in local contact (`d <= 1`). It never authorizes distant pursuit.
- a distant candidate inside a strong `BACKGROUND_DYNAMIC` region produces `BACKGROUND_HOLD`, not movement.

## Safety

- Default duration: 25 seconds.
- `F12`: global emergency stop.
- Foreground loss stops control.
- `finally` releases R and all arrows.
- every cycle also returns explicitly to R before any directional pulse.
- H is never sent.
- Automatic post-combat V is not enabled yet.

## Command

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03.py --seconds 25 --log kage_pilot_live_test_3.jsonl
```

## Useful safety states in logs

- `MOVE_CONFIRM`: target/direction is still waiting for confirmation.
- `MOVE_PULSE`: directional pulse authorized.
- `MOTION_BURST_HOLD`: likely impact/particles; movement blocked.
- `NO_PROGRESS_HOLD`: pursuit was active but distance did not improve.
- `MOVE_COOLDOWN`: short pause before reconsidering pursuit.
- `MEMORY_HOLD`: memory exists without enough vision to pursue.
- `BACKGROUND_HOLD`: candidate is inside a strong dynamic-background region.
