# Enemy Perception replay correction

## Root cause

The previous pipeline required both a visually recognized Player and an almost-perfect empty background before it would create any entity. The physical session proved this was too strict: the terrain classifier already reported an NPC at about 94.7%, but the observation was discarded because the background score stayed below 98.5%.

## Corrected architecture

```text
capture or replay frame
→ locate Player
   → visual confirmation
   → temporal prediction
   → calibrated playfield anchor fallback
→ classify 64 px cells
→ Path A: NPC >= semantic threshold creates a semantic candidate immediately
→ Path B: known empty appearance produces a residual candidate
→ fuse semantic and residual evidence
→ require final anchor inside Manhattan D<=4
→ create/update Track ID
→ analyze movement, approach and hostility
```

A semantic NPC is evidence that a non-Player entity exists. It is not evidence that the entity is hostile. Hostility remains temporal and behavior-based.

## Player anchor

The fallback is derived from the playable field, not the full HWND. Defaults:

```text
X = 0.50 of captured width
Y = 0.57 of playfield height
```

Both ratios and an explicit grid column/row are configurable. The overlay always states whether the source is `VISUAL_CONFIRMED`, `TEMPORAL_PREDICTED` or `CALIBRATED_ANCHOR_FALLBACK`.

## Background catalogue

Schema 3 groups empty appearances by:

```text
semantic terrain class + visual appearance cluster
```

World coordinates remain metadata only. The match score combines:

```text
70% foreground-tolerant similarity
30% raw whole-tile similarity
```

This permits a character over the correct terrain to remain `USABLE` while preventing an unrelated scene from becoming a strong match merely because a small pixel subset looks alike.

Background levels:

```text
STRONG  >= 0.95
USABLE  >= 0.88
WEAK    >= 0.70
NONE    <  0.70
```

`WEAK` evidence is diagnostic only. It is drawn in the difference composite but cannot independently create a residual entity.

## Scene consensus

Repeated empty-looking terrain may be learned when the same appearance:

- occurs in at least eight eligible cells;
- repeats for four stable frames;
- excludes Player, NPC, HUD and dynamic classes;
- is grouped by visual similarity.

## Offline replay

```powershell
.\navigation_lab\scripts\run_enemy_perception_replay.ps1 `
  -InputZip "C:\path\enemy_detection_physical_test_03.zip" `
  -Profile "default" `
  -RegionId "mapping_input_calibration" `
  -PlayerAnchorMode "Auto" `
  -PlayerAnchorXRatio 0.50 `
  -PlayerAnchorYRatio 0.57 `
  -SemanticEntityThreshold 0.90 `
  -BackgroundStrongThreshold 0.95 `
  -BackgroundUsableThreshold 0.88 `
  -BackgroundDiagnosticThreshold 0.70 `
  -InterestRadiusCells 4 `
  -DebugMode "Balanced" `
  -DebugStride 5 `
  -OutputSession "enemy_detection_replay_fix_01"
```

The replay reads `00_raw_window.png` and the recorded semantic cell metadata, never opens the game HWND, never modifies the source session and writes `replay_report.json` plus `replay_report.csv`.

## Physical-session metadata regression

Using the 47 provided frame records and the corrected Player/semantic policies:

```text
Player visual frames:       5
Player fallback frames:    42
Frames without Player:      0
Semantic NPC observations: 33
Track lifecycles created:   2
Longest continuity:        31 frames
Maximum tracked distance:   3
Tracks with D>4:            0
HUD tracks:                 0
```

The two track lifecycles are expected because the NPC leaves the D<=4 scope long enough to exceed the configured TTL before reappearing near the Player.

This metadata regression validates the key architectural correction. The repository replay command remains the authoritative end-to-end validation on the user's Windows profile because it also exercises persisted tile crops, local profile paths, debug output and timing.

## Balanced debug

Balanced mode writes:

- `frame.json` and events for every frame;
- `01_grid_overlay.png` for every frame;
- all nine images every `DebugStride` frames;
- all nine images on state-changing events such as Player source changes, entity creation/movement, hostility changes, new background clusters and errors.

PNG writes run on a bounded background queue. A persistent semantic NPC does not force a full nine-image set every frame.

## Safety boundary

This branch remains passive. `ATTACK_RECOMMENDED` is an explainable output event only. No keyboard or mouse command is sent to the game.
