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
- `player` — the locally controlled character, shown as `P` and reserved as the future localization anchor;
- `npc` — living or potentially moving non-player character occupying the cell at observation time;
- `transition` — door, portal, stairs or region transition;
- `danger` — hazardous terrain or area;
- `ignore_dynamic` — animation, particle effect or other content without a useful persistent identity;
- `unknown` — no sufficiently similar taught example exists.

`player`, `npc` and `blocking_object` are deliberately separate:

```text
P = controlled character and future position anchor
N = non-player living/dynamic entity
B = non-living physical obstruction
I = effect or animation to ignore
```

A player or NPC may cover the ground in the current capture, but neither must turn the underlying terrain into a permanent wall. Later world-stitching logic will combine repeated observations to recover the terrain beneath dynamic entities.

## Classification menu

The entire right-side classification menu is vertically scrollable. Use the mouse wheel over the panel or the visible scrollbar to access:

- recognition threshold;
- unknown-cell queue;
- selected crop preview;
- all classification buttons;
- per-category summary.

The application also opens with a larger default window, while the scrollbar keeps every option reachable on smaller displays or Windows scaling above 100%.

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
- the `player` cell as a localization candidate;
- player/camera displacement;
- repeated observations of the same terrain;
- confidence and conflict resolution;

to place classified cells into persistent world coordinates.

Real route planning and autonomous navigation remain blocked until that stitching step is physically validated.
