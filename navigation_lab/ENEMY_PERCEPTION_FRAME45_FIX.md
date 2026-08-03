# Frame 45 correction — visual backgrounds and local tracking

## Core semantic correction

`02_background_composite.png` is not a reconstruction of the world and does not ask where a tile was previously seen or what surrounded it.

For every eligible current cell, the laboratory now asks:

```text
Have I seen this empty tile, or something visually similar, before?
```

The empty-background catalogue is grouped by semantic terrain class. `world_cell` is retained only as source/debug metadata and is not the primary lookup key.

A robust similarity score ignores a small localized fraction of the largest pixel differences so a foreground sprite can still be matched against its empty terrain. The normal untrimmed similarity is also preserved for diagnostics.

## Processing scope

```text
full HWND capture
→ locate Player using PR 24
→ exclude the HUD below PlayfieldBottomRatio
→ process expensive visual operations only inside Manhattan D<=5
→ require the final entity anchor inside Manhattan D<=4
→ validate candidate size and geometry
→ classify
→ track
→ analyze hostility
```

The D<=5 ring exists only to complete a sprite mask at the edge. It cannot create a tracked entity whose anchor is outside D<=4.

## Background acceptance

A visual background match must satisfy:

- same semantic terrain class when the current cell is already classified as terrain;
- robust similarity at or above `BackgroundMatchThreshold`;
- stable frame;
- inside the playfield and local processing ROI;
- not the Player cell;
- changed ratio and mean difference below the structural-mismatch limits.

A full-cell or large structural replacement is recorded as `structural_background_mismatch` and never becomes an entity.

## Candidate validation

Before classification or tracking, candidates are rejected for:

- touching the HUD;
- missing a world anchor;
- anchor outside D<=4;
- too many covered cells;
- bounding box wider or taller than the configured cell limits;
- excessive pixel area;
- extreme aspect ratio.

Rejected candidates are shown only in `05_components_overlay.png` and recorded in `frame.json` under `candidate_rejections`.

## Debug counters

Each frame records:

```text
total_cells
cells_inside_playfield
cells_inside_processing_roi
background_matches_accepted
background_matches_rejected
raw_components
candidates_rejected
valid_entities
tracks_created
```

## Background schema

The visual catalogue uses schema version 2. Schema version 1 represented the previous coordinate-driven model and is not loaded silently.

Use the safe reset once when moving to this implementation:

```powershell
-ResetBackgroundReferences
```

This removes only:

```text
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>\enemy_perception\<region_id>\backgrounds
```

It does not remove grid calibration, Tile Map Maker knowledge or continuous mapping state.

`-ResetUnknownEntityKnowledge` clears only grouped unknown entities and preserves taught entity examples.

## Frame 45 regression

The required regression is the behavior represented by the previous `ENT-000045`:

```text
Player world cell: [0, -1]
target world cell: [0, -2]
Manhattan distance: 1
local bounding box: accepted
tracking: allowed
```

The exact Track ID is not required to remain the same. The D=1 localization and local extraction behavior must remain.

## Recommended physical command

```powershell
.\navigation_lab\scripts\run_enemy_perception_lab.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -Profile "default" `
  -RegionId "mapping_input_calibration" `
  -CaptureInterval 0.20 `
  -AutoThreshold 0.95 `
  -ReviewThreshold 0.90 `
  -BackgroundMatchThreshold 0.985 `
  -PlayfieldBottomRatio 0.75 `
  -InterestRadiusCells 4 `
  -OverlayPixelThreshold 24 `
  -MinChangedPixelRatio 0.03 `
  -MinComponentArea 12 `
  -MaxEntityCoveredCells 9 `
  -MaxEntityWidthCells 3 `
  -MaxEntityHeightCells 3 `
  -TrackTtlFrames 10 `
  -DebugFrames `
  -KeepWindowVisible `
  -ResetBackgroundReferences `
  -SessionName "enemy_detection_physical_test_03"
```

Use `-ResetBackgroundReferences` only for the first run after this schema change. Remove it from later commands so the new visual catalogue can persist.
