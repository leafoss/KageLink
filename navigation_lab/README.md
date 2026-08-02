# Kage Navigation Lab — PR 24

Independent laboratory for mapping, localization, route planning and safe navigation experiments. It does **not** import or control KageLink.

## Current priority: continuous semantic world mapping

PR 24 now combines the calibrated square grid, taught tile examples and the Player anchor to build a persistent relative world map while the user plays.

```text
capture target HWND in background
→ wait for a settled frame
→ crop every calibrated cell
→ classify known tiles
→ locate Player
→ stitch cells into relative world coordinates
→ group confidence < 0.90 for later review
```

The program does not open questions over the fullscreen game. Unknown crops are grouped by visual similarity and reviewed later with `F7`.

Implemented:

- square-grid calibration saved per profile/region;
- exact target-window capture through the game HWND, with no monitor screenshot fallback;
- visual crop and explainable feature descriptor for every complete calibrated cell;
- semantic categories for Player, NPC, walkable terrain, walls, jutsu terrain, blocking objects, transitions, danger and ignored/dynamic content;
- confirmed (`>= 0.95`), provisional (`>= 0.90`) and unknown (`< 0.90`) confidence bands;
- grouped review queue instead of one interruption per unknown cell;
- separate persistent-terrain and dynamic-occupant layers;
- relative Player coordinates using screen-cell movement or accumulated inverse camera translation;
- moving-frame rejection so scrolling/blurry frames are not written into the world map;
- persistent ASCII world map, unknown queue and learned PNG/JSON examples;
- passive `F7` review hotkey;
- simulator, occupancy grid, world graph, A*, frontier foundation and state machine retained as later layers;
- no keyboard or mouse output adapter.

Still intentionally blocked:

- assisted navigation against the live game;
- autonomous keyboard control;
- destination routing based on the live world map;
- automatic region-transition stitching;
- production-grade relocalization after teleport/death/restart.

## Requirements

- Windows 10 or later;
- Python 3.11 or later;
- Tkinter included in the Python installation;
- `Shinobi Story Online` visible and not minimized during capture.

## Setup

```powershell
.\navigation_lab\scripts\setup_navigation.ps1
```

## 1. Calibrate the square grid

```powershell
.\navigation_lab\scripts\run_grid_calibration.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -RegionId "mapping_input_calibration" `
  -Profile "default"
```

## 2. Teach representative cells

```powershell
.\navigation_lab\scripts\run_tile_map_maker.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -RegionId "mapping_input_calibration" `
  -Profile "default" `
  -SimilarityThreshold 0.92
```

Teach at least the Player and representative walkable/wall terrain before continuous mapping.

## 3. Run continuous background mapping

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

The mapper starts and minimizes. Play normally. Press `F7` when you want to review grouped unknown crops. Closing and reopening without `-NewMap` restores the relative world map.

Read [`CONTINUOUS_SEMANTIC_MAPPER.md`](CONTINUOUS_SEMANTIC_MAPPER.md) for the complete confidence, layering, localization and physical-validation rules.

## Legacy diagnostic observer

```powershell
.\navigation_lab\scripts\run_mapping_observer.ps1
```

## Desktop simulator

```powershell
.\navigation_lab\scripts\run_simulator.ps1 `
  -Scenario 12_route_replanning `
  -Language pt-BR `
  -DebugWindow
```

## Test

```powershell
.\navigation_lab\scripts\run_tests.ps1
```

Windows data is stored under:

```text
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>
```
