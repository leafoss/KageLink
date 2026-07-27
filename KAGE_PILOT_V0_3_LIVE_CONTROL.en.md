# Kage Pilot v0.3 — Live Control Gate 3 (EN-US)

## Goal

Close the first autonomous Dojo cycle without changing the already validated combat core:

```text
COMBAT
→ authoritative chat victory
→ R OFF
→ locate Dojo leader
→ become adjacent
→ V ON
→ recover HP/Chakra
→ V OFF
→ READY
```

## Preserved combat behavior

v0.3 has already validated in the real game:

- 32×32 logical GRID;
- hybrid TARGET with contact memory;
- water/background filtering;
- impact-particle protection;
- `R` as the BYOND combat base state;
- dead-man movement pulses;
- knockback recovery;
- explicit facing correction;
- guarded real `H`;
- first autonomous victory.

During combat:

- `R` is the only key that may remain logically active;
- arrows are short pulses, never persistent held state;
- `H` is always a short tap and only fires in validated melee;
- before `H`, Pilot forces a fresh facing pulse toward TARGET;
- after `H`, `H_SETTLE_HOLD` prevents reacting to its own particles;
- `MOTION_BURST_HOLD` blocks movement/facing/H during wind/particle spikes while keeping only R.

## Authoritative victory from game chat

Victory is **not** inferred from `target=none` or visual disappearance of the enemy.

Kage Pilot reads Shinobi Story Online chat directly and observes only text appended after the current fight starts.

The authoritative family is:

```text
<any name/rank> has been Knocked-Out
```

Observed example provided by the user:

```text
Jounin: Tamura, Seijun has been Knocked-Out
```

The matcher also tolerates `has been knocked out`, but does not accept only `knocked down` or TARGET disappearance.

When the message arrives:

```text
VICTORY_CHAT
→ release_all()
→ R OFF immediately
→ leave COMBAT
→ enter POST_COMBAT
```

Everything already present in chat before the fight is baseline only and cannot create a retroactive victory.

## Post-combat — Dojo leader

Post-combat uses the real Dojo leader sprite supplied by the user as a template.

State:

```text
SEEK_DOJO_LEADER
```

Rules:

- search the sprite inside the captured arena;
- require confirmation across multiple frames;
- when the NPC is not visible, do not walk blindly;
- navigate with short arrow pulses and **no R**;
- map PLAYER and leader to the 32×32 GRID;
- any of the eight adjacent cells is valid;
- Chebyshev distance `<= 1` means the character is next to the NPC.

## Meditation with V

`V` is a **toggle**, never a held key.

When adjacent to the leader:

```text
V TAP
→ enter meditation
→ no key remains held
```

While meditating, Kage Pilot reads HP and Chakra bars from the GAME HUD.

Current requested thresholds:

```text
HP >= 90%
AND
Chakra >= 50%
```

Both thresholds must remain valid for multiple consecutive readings.

When both are reached:

```text
V TAP
→ leave meditation
→ READY
```

There is no `V HOLD`.

## Dead-man movement

For example, `MOVE_RIGHT` is:

```text
base state
↓
RIGHT for ~90 ms
↓
RIGHT OFF obligatorily
↓
fresh perception required for another step
```

A bad decision cannot leave an arrow permanently held.

## Pursuit confirmation and watchdog

- distant target/direction must remain coherent before the first movement pulse;
- distant `ENTITY ID` switch resets confirmation;
- lack of GRID progress produces `NO_PROGRESS_HOLD`;
- distant `CONTACT_MEMORY` never authorizes pursuit;
- strong dynamic background blocks pursuit;
- tiny particles have no authority for distant navigation.

## Safety

- `F12`: global emergency stop;
- foreground loss stops control;
- `finally` releases R/H/arrows;
- chat victory releases every key before post-combat begins;
- post-combat never re-enables R;
- when the leader cannot be located, the character remains still;
- post-combat timeout never invents successful recovery;
- if this runtime started meditation and post-combat expires normally, V is tapped once so the game is not left in a persistent meditation state;
- F12 sends no additional action after the emergency stop.

## Current command

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03.py --seconds 60 --log kage_pilot_live_test_5.jsonl
```

Post-combat defaults:

```text
chat poll:               0.25 s
leader threshold:        0.72
leader confirmation:     2 frames
HP target:               90%
Chakra target:           50%
recovery confirmation:   3 frames
post-combat timeout:     120 s
V pulse:                 0.08 s
```

## Useful log states

Combat:

- `MOVE_CONFIRM`
- `MOVE_PULSE`
- `FACE_RECOVER`
- `H_FIRE`
- `H_SETTLE_HOLD`
- `MOTION_BURST_HOLD`
- `NO_PROGRESS_HOLD`
- `MOVE_COOLDOWN`
- `MEMORY_HOLD`
- `BACKGROUND_HOLD`

Post-combat:

- `VICTORY_CHAT`
- `SEEK_DOJO_LEADER`
- `START_MEDITATION`
- `MEDITATING`
- `READY`
