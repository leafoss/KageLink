# Kage Pilot v0.3j — Stationary trainer acquisition

**Date:** 2026-07-29  
**Status:** automated implementation complete; physical validation pending

## Observed failure

In a new 20-round run, round 1 never recorded a trainer visual confirmation. The search waited only briefly and entered its concentric rings, reaching 19 logical cells before foreground was lost.

```text
TRAINER_SEARCH state=SEARCH_WAIT
TRAINER_SEARCH state=SEARCH_LEADER move=up
...
ring=3/29 cells=19
DOJO_REQUEST_STOPPED_FATAL: GameControlError: FOREGROUND_LOST
```

Commit comparison confirmed that the KO identity-buffer hotfix did not modify trainer detection or trainer search. The run exposed an older weakness: movement pulses could begin almost continuously before two stable trainer frames were available.

This is especially likely when the player starts partially overlapping the trainer and hides part of the sprite.

## New flow

```text
activate game window
→ release every input
→ 1.5 s stationary visual acquisition
→ if no trainer: one right lateral reveal pulse
→ 0.75 s stationary visual acquisition
→ concentric search only when still required
→ after every search pulse: 0.35 s stationary visual dwell
```

## Invariants

- no click occurs before two current visual confirmations;
- the reveal pulse occurs at most once per request;
- the reveal pulse is lateral, never `up` or `down`;
- every key remains released during scan holds;
- concentric search remains available when starting far from the trainer;
- F12 still interrupts immediately;
- foreground loss still stops the request safely;
- KO buffering, combat, post-combat, recovery and dialog behavior are unchanged.

## Telemetry

```text
TRAINER_SCAN_HOLD phase=INITIAL_SCAN_HOLD
TRAINER_REVEAL_PROBE direction=right
TRAINER_SCAN_HOLD phase=REVEAL_SCAN_HOLD
TRAINER_SEARCH ...
TRAINER_SCAN_HOLD phase=POST_MOVE_SCAN_HOLD
TRAINER_VISUAL_CONFIRM hits=1/2
TRAINER_VISUAL_CONFIRMED
```

## Files

```text
pc_agent/kage_pilot/trainer_search_v03k.py
pc_agent/kage_pilot/dojo_fight_v03i.py
tests/test_kage_pilot_v03k_trainer_search_gate.py
.github/workflows/kage-pilot-v03.yml
```

## Remaining gate

Validate in the real game while starting directly below or partially overlapping the trainer. The PR remains a draft and is not merged.
