# Kage Pilot v0.3 — Live Control Gate 1 (EN-US)

## Goal

Validate real combat with the smallest possible automated action set after the Entity Observer and Shadow Combat stages.

At this stage Kage Pilot **sends real keys**, but only:

- `R` as the combat base state, using the already validated BYOND repeat pattern;
- directional arrows for approach/recovery;
- short direction pulses to correct facing in melee.

`H` remains **Shadow Mode only**. The console may print `H_READY(SHADOW)`, but no H key is sent.

## Movement rules

- `d <= 1 cell`: MELEE. Keep R and only correct facing with a short pulse when needed.
- `d >= 2 cells`: APPROACH/RECOVER. Keep R and hold the arrow toward the TARGET.
- TARGET temporarily unavailable: keep R but do not move blindly.
- CONTACT_MEMORY preserves the last visually confirmed direction.

The rule `d >= 2 => RECOVER` is deliberate: it prevents the v0.2 failure where Leafos was knocked back and kept attacking empty space.

## Safety

- Default duration: 25 seconds.
- `F12`: global emergency stop.
- Foreground loss stops control; this stage does not try to steal focus back.
- `finally` always releases R and all arrows.
- H is never sent.
- Automatic post-combat V is not enabled yet.

## Command

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03.py --seconds 25 --log kage_pilot_live_test_1.jsonl
```

## Success criteria

1. R stays active throughout combat.
2. When the enemy crosses sides, Leafos corrects facing without continuously walking into the target.
3. After knockback, `d >= 2` produces RECOVER/MOVE in the correct direction.
4. During a short TARGET loss, Leafos holds position instead of chasing noise.
5. `H_READY(SHADOW)` may appear, but H is not executed in this stage.
