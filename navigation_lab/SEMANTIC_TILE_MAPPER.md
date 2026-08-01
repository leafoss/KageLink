# Semantic Tile MapMaker — grid-driven active learning

The original movement-first MapMaker is not the active PR 24 milestone anymore. The current approach begins with the calibrated visual grid and classifies every complete square cell visible in the `Shinobi Story Online` client.

## Core rule

```text
calibrated game frame
→ crop every complete square grid cell
→ compare each crop with taught examples
→ confident match: classify automatically
→ no confident match: keep UNKNOWN and ask the player
```

No unknown cell is silently assumed to be walkable or blocked.

## Categories

- `walkable` — normal terrain that can be crossed;
- `wall` — structural terrain that is permanently impassable;
- `walkable_with_jutsu` — terrain that requires a technique or special movement;
- `blocking_object` — non-living physical object currently occupying or blocking the cell;
- `npc` — living or potentially moving non-player character occupying the cell at observation time;
- `transition` — door, portal, stairs or region transition;
- `danger` — hazardous terrain or area;
- `ignore_dynamic` — player sprite, animation, effect or other content that should not become terrain knowledge;
- `unknown` — no sufficiently similar taught example exists.

`npc` is deliberately separate from `blocking_object`. An NPC may block movement now, but its presence must not turn the underlying terrain into a permanent wall. Later world-stitching logic will treat NPC occupancy as a dynamic observation that can disappear on a subsequent capture.

## Recognition method

The first implementation is deliberately explainable and local. For each cell crop it extracts:

- HSV color distribution;
- normalized grayscale structure;
- edge distribution;
- mean and standard deviation of the color channels.

The resulting vector is compared with every taught example. The nearest example is accepted only when its similarity reaches the configured threshold. The interface always displays the similarity and the matched example ID.

This is an active-learning foundation, not a claim that the game world is solved. Animated sprites, lighting changes and overlapping objects can still make a cell uncertain; those cells remain in the teaching queue.

## Fullscreen workflow

1. Calibrate and save the square grid for the selected profile and region.
2. Start the Semantic Tile MapMaker.
3. Minimize it and return to the fullscreen game.
4. Press `F8` while the game is foreground.
5. Return with `Alt+Tab`.
6. Inspect the colored grid and the unknown-cell queue.
7. Select an unknown crop and classify it.
8. The whole captured screen is re-evaluated immediately using the new example.
9. Repeat until the remaining unknown cells are genuinely new or dynamic.

The `F8` listener is passive. Capture is tied to the target HWND; the desktop and preview window are not used as the game image source.

## Run

```powershell
.\navigation_lab\scripts\run_tile_map_maker.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -RegionId "mapping_input_calibration" `
  -Profile "default" `
  -SimilarityThreshold 0.92
```

The tool requires a saved calibration created with `run_grid_calibration.ps1` using the same `Profile` and `RegionId`.

## Saved data

```text
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>\
  calibrations\<region>_grid.json
  tile_knowledge\<region>.json
  tile_knowledge\<region>\examples\<example_id>.png
```

Each learned example keeps its category, visual feature vector, crop path, creation time and optional notes.

## What this milestone does not do yet

The screen classification is not yet a stitched world map. It produces a semantic matrix for one captured viewport. The next milestone will combine:

- the semantic cell matrix;
- player/camera displacement;
- repeated observations of the same terrain;
- confidence and conflict resolution;

to place classified cells into persistent world coordinates.

Real route planning and autonomous navigation remain blocked until that stitching step is physically validated.
