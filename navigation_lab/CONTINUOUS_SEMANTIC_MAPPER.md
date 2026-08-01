# Continuous Semantic Mapper — background world construction

This is the active PR 24 physical milestone after grid calibration and manual tile teaching.

## Runtime flow

```text
capture only the Shinobi Story Online HWND
→ split the settled client frame into calibrated square cells
→ classify each crop using taught examples
→ locate the Player cell
→ estimate relative player/world displacement
→ place stable classified cells in relative world coordinates
→ preserve terrain and occupants as separate layers
→ group crops below the review threshold
→ save the map and review queue
```

The mapper never sends keyboard or mouse input.

## Confidence policy

Default thresholds:

```text
confidence >= 0.95  confirmed automatic classification
0.90 <= confidence < 0.95  provisional evidence
confidence < 0.90  UNKNOWN review group
```

Unknown crops are grouped by visual similarity. Many occurrences of the same unknown tile therefore produce one review item rather than one pop-up per cell.

The program never opens a classification question over the fullscreen game. Press `F7` to bring the review window forward when convenient. Mapping automatically stops consolidating frames while the game is not foreground.

## World layers

Each relative world coordinate can contain:

- persistent terrain evidence: walkable, wall, walkable with jutsu, transition or danger;
- dynamic occupants: Player, NPC, blocking object or ignored animation/effect.

Player and NPC observations never overwrite the terrain below them. Dynamic occupants expire after they are no longer observed; terrain evidence remains.

## Localization policy

The Player category is the primary screen anchor.

- If the Player moves between grid cells while the scenery remains fixed, the mapper uses the Player screen-cell delta.
- If the Player stays near the center while the camera follows, phase correlation accumulates inverse scenery displacement until it reaches a logical tile.
- Frames with accepted camera translation are treated as moving frames. They update odometry but are not consolidated into the world map.
- Classified cells are written only from settled frames with a recognized Player anchor.

This localization remains a physical-test hypothesis. The map must be reviewed for drift before navigation work resumes.

## Start

```powershell
.\navigation_lab\scripts\run_continuous_mapper.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -RegionId "mapping_input_calibration" `
  -Profile "default" `
  -CaptureInterval 0.75 `
  -AutoThreshold 0.95 `
  -ReviewThreshold 0.90 `
  -GroupingThreshold 0.965
```

The mode requires:

1. a saved grid calibration for the same profile and region;
2. saved tile knowledge containing at least Player and representative terrain examples.

The window starts, begins mapping and minimizes. Play normally. Press `F7` when you want to review grouped unknown crops.

Use `-NewMap` only when intentionally starting a fresh relative world map. Existing learned tile examples are stored separately and are not deleted by that flag.

## Interface symbols

```text
P  current player world position
.  walkable terrain
#  wall
J  walkable with jutsu
T  transition
!  dangerous terrain
N  NPC occupant
B  blocking-object occupant
?  unknown or unobserved
```

## Persistent data

```text
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>\
  calibrations\<region>_grid.json
  tile_knowledge\<region>.json
  tile_knowledge\<region>\examples\*.png
  continuous_mappings\<region>.json
  continuous_mappings\<region>\unknown_groups\*.png
```

## First physical approval gate

Test in a small safe area before exploring a large region:

1. Player is recognized in most settled frames.
2. Remaining still does not move the world coordinate.
3. Moving one tile changes the relative Player coordinate by one tile.
4. Returning to the starting tile returns close to the original coordinate.
5. Walkable and wall terrain remain aligned after a short loop.
6. NPCs appear as dynamic `N` occupants and disappear after leaving the observation area.
7. Unknown groups accumulate without interrupting gameplay.
8. Teaching one group through `F7` improves subsequent captures.
9. Closing and reopening restores the relative map and review queue.

Do not enable assisted or autonomous navigation until this gate is physically approved.
