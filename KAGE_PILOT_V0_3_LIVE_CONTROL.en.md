# Kage Pilot v0.3 — Live Control Gate 2 (EN-US)

## Goal

Validate fuller real combat while preserving the runaway protections and enabling the first guarded real use of `H`.

At this stage Kage Pilot sends:

- `R` as the combat base state;
- short arrow pulses for approach/recovery;
- short direction pulses to correct melee facing;
- `H` as a short tap, only inside a validated skill window.

## Dead-man movement rule

Arrow keys are never persistent held state. Every iteration explicitly returns to `R` before any directional pulse.

```text
R
↓
R + RIGHT for ~90 ms
↓
R again
```

Continuing movement requires fresh perception authorization on later cycles.

## Facing recovery after impact/knockback

Enemy hits may push Leafos and physically turn the character to the wrong direction. TARGET geometry can still be correct while actual facing has changed.

Either of these situations now arms a mandatory facing correction:

- APPROACH/RECOVER;
- `MOTION_BURST_HOLD` caused by impact/particles.

When the system returns to `d <= 1`, the first melee frame forces exactly one fresh pulse toward the enemy even when that direction matches the cached facing.

The log state is:

```text
FACE_RECOVER
```

## Guarded real H

`H` is enabled only when:

- TARGET is in melee (`d <= 1`);
- current visual confirmation exists (`VISIBLE`/`OCCLUDED`);
- the target is not only `CONTACT_MEMORY`;
- Enemy Score meets the minimum;
- logical engagement has been stable long enough;
- cooldown has finished;
- neither `MOTION_BURST_HOLD` nor `H_SETTLE_HOLD` is active.

Before every real H, the controller forces a fresh facing pulse toward TARGET. Physical sequence:

```text
R
↓
R + direction for ~55 ms
↓
R
↓
R + H for ~65 ms
↓
R
```

The log reports:

```text
H_FIRE
```

H can be disabled for regression testing with `--disable-h`.

## H_SETTLE_HOLD

The jutsu itself can create visual animation/particles. After every H there is a default settling window of about `0.55 s`:

```text
H_SETTLE_HOLD
→ R remains active
→ no arrow movement
→ no new facing pulse
→ no new H
```

This prevents the controller from reacting to its own jutsu visual effect.

## Pursuit confirmation and watchdog

- a distant target/direction must appear in at least 2 consecutive decisions before the first movement pulse;
- a distant `ENTITY ID` switch resets confirmation;
- if GRID distance fails to improve for about 1.15 s, use `NO_PROGRESS_HOLD`;
- `CONTACT_MEMORY d >= 2` never authorizes pursuit;
- a distant target inside strong `BACKGROUND_DYNAMIC` produces `BACKGROUND_HOLD`.

## Impact/particle guard

`MotionBurstGuard` monitors active grid cells and entity population. A sudden spike produces `MOTION_BURST_HOLD` for about `0.75 s`, leaving only R active.

That hold also arms one mandatory facing correction when reliable melee resumes.

## Safety

- Default duration: 25 seconds.
- `F12`: global emergency stop.
- Foreground loss stops control.
- `finally` releases R, arrows and H.
- arrows and H are always short pulses, never persistent held states.
- automatic post-combat V is still disabled.

## Command

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03.py --seconds 45 --log kage_pilot_live_test_4.jsonl
```

## Useful log states

- `MOVE_CONFIRM`: waiting for movement confirmation.
- `MOVE_PULSE`: authorized approach/recovery pulse.
- `FACE_RECOVER`: mandatory facing correction after knockback/impact.
- `H_FIRE`: H was physically sent.
- `H_SETTLE_HOLD`: short pause after own H animation.
- `MOTION_BURST_HOLD`: likely impact/particles; only R remains active.
- `NO_PROGRESS_HOLD`: distance failed to improve.
- `MOVE_COOLDOWN`: pause before reconsidering pursuit.
- `MEMORY_HOLD`: memory exists without enough vision to pursue.
- `BACKGROUND_HOLD`: candidate is inside strong dynamic background.
