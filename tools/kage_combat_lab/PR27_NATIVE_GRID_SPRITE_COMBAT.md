# PR27 — Native 64×64 Sprite Combat

PR27 is an isolated rewrite of the combat subprocess, stacked directly on the current PR26 branch.

## Preserved outer lifecycle

```text
find Trainer
→ interact
→ dialog / OK
→ PR27 combat subprocess
→ authoritative KO
→ find Trainer
→ protected meditation
→ READY / next round
```

The PR26 combat runtime patch chain is not installed by the PR27 entrypoint.

## Mandatory pipeline

```text
native DreamSeeker client frame, BGR, no JPEG or resize
→ crop arena
→ native 64×64 cells
→ one baseline per cell
→ one difference mask per cell
→ mark changed cells
→ group neighbouring cells only as search addresses
→ extract sprite fragments inside each changed cell
→ compare appearance and temporal continuity
→ create or preserve TrackedSprite ID
→ classify PLAYER / ENEMY / NPC / UNKNOWN
→ calculate direction and distance only after identity
→ plan turn, chase or attack
```

## Central rule

> The 64×64 cell is the unit of visual truth. A group only tells the system which cells to search. The sprite owns identity. A foot point is not identity authority.

`CellSearchGroup` contains only:

```python
CellSearchGroup:
    group_id
    cells
```

## Safety modes

- `PERCEPTION_ONLY`: full perception and planning; all game inputs blocked.
- `FACE_ONLY`: short directional pulse only; chase, `R` and `H` blocked.
- `CONTROL_ENABLED`: explicit operator mode for a confirmed, visible enemy ID.

The launcher defaults to `PERCEPTION_ONLY`.

## Scene changes

A global change suspends combat, invalidates baselines and waits for stable per-cell samples. PR27.1 does not use optical flow or phase correlation.

## Debug and logs

The overlay shows native cells, changed ratios, search groups, fragments, visual IDs, classifications, target and planned action. `P` or Space pauses; `Q` or Escape closes.

JSONL logs record native size, arena rectangle, each changed cell, groups as cell addresses, fragments and source cells, tracks, target, planned action, physical action and decision reason.

## Supervised test

```powershell
.\run_pr27_native_sprite_combat.ps1 `
  -PerceptionOnly `
  -DebugOverlay `
  -Rounds 1 `
  -CombatSeconds 120 `
  -PostCombatTimeout 240 `
  -DialogDelay 5 `
  -SpawnDelay 5 `
  -TrainerSearchTimeout 90
```

PR27.1 is intended for supervised `PERCEPTION_ONLY` validation before any control-enabled test.
