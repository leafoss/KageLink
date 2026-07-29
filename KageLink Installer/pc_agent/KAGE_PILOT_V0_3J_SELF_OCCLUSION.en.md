# Kage Pilot v0.3j — Trainer self-occlusion recovery

**Date:** 2026-07-29  
**Status:** implementation and automated tests under validation; physical test pending  
**Scope:** post-combat, immediately before meditation authorization

## Visual evidence

A real screenshot showed Leafos standing directly below the Dojo Trainer. In this position, the player sprite covers part of the trainer's legs, seat and lower template region.

This explains the observed log:

```text
current trainer visual at d=1
→ Leafos arrives directly below
→ template becomes partially hidden
→ detector falls back to memory at d=0/d=1
→ V remains blocked for safety
→ post-combat waits for a new current visual
```

The rule that memory never authorizes `V` remains correct and is preserved.

## New policy

When visual reacquisition has already started and all conditions below are true:

1. the last real trainer visual is recent;
2. memory still reports `d <= 1`;
3. `V` has not been authorized;
4. no self-occlusion escape has been sent during this recovery;
5. at least one perpendicular direction is not temporarily blocked;

then the engine emits:

```text
SELF_OCCLUSION_ESCAPE
```

with exactly one short cardinal pulse.

It then emits:

```text
SELF_OCCLUSION_WAIT
```

with no movement and no `V` while the detector tries to obtain a current visual again.

## Direction selection

The escape direction is perpendicular to the player → trainer vector:

```text
Trainer above or below
→ try right/left

Trainer left or right
→ try down/up
```

The first option is the direction with more available arena space. If it is temporarily blocked, the opposite perpendicular direction is tried. If both are blocked, no movement is forced and the existing bounded visual search continues.

For the screenshot case:

```text
Trainer
   ↑
Leafos
```

`up` is explicitly forbidden as the self-occlusion pulse. The result must be `left` or `right`.

## Safety invariants

The change does not allow:

- `V` from memory;
- more than one self-occlusion pulse during one recovery;
- held direction keys;
- a held mouse button;
- another trainer click;
- any combat behavior change;
- `H`, `R` or offensive actions during post-combat;
- forced movement when both perpendicular directions are blocked.

Meditation still requires:

```text
2 current adjacent visual confirmations
→ START_MEDITATION
→ V_TAP
```

## Expected telemetry

```text
POST SELF_OCCLUSION_ESCAPE leader_score=... d=0 move_pulse=left V_WAIT ...
reason=POSSIBLE_SELF_OCCLUSION...

POST SELF_OCCLUSION_WAIT leader_score=... d=0 move_pulse=- V_WAIT ...

POST SEEK_LEADER ... confirming adjacent trainer visual
POST START_MEDITATION ... V_TAP
```

If current vision does not return after the short settle:

```text
REACQUIRE_VISUAL_WAIT
→ REACQUIRE_LEADER_VISUAL
```

The previous bounded visual search remains the fallback.

## Files

```text
kage_pilot_live_v03j_round.py
tests/test_kage_pilot_v03j_self_occlusion.py
.github/workflows/kage-pilot-v03.yml
```

## Regression coverage

- player below trainer gets a lateral pulse, never `up`;
- only one `SELF_OCCLUSION_ESCAPE` per recovery;
- `SELF_OCCLUSION_WAIT` neither moves nor taps `V`;
- two current visuals after the escape authorize meditation;
- trainer to the left/right produces a vertical escape;
- memory without a recent visual uses the previous bounded search;
- two blocked perpendicular directions do not force movement.

## Physical gate

Real-game validation must confirm:

- [ ] `SELF_OCCLUSION_ESCAPE` appears when Leafos hides the trainer;
- [ ] the pulse is lateral in the below-trainer scenario;
- [ ] the character does not walk into the trainer;
- [ ] at most one pulse occurs;
- [ ] `V` occurs only after two current visuals;
- [ ] recovery finishes in `READY`;
- [ ] the loop continues to the next round;
- [ ] no key leaks into PowerShell.

The PR remains a draft and is not merged.
