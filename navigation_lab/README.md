# Kage Navigation Lab — PR 24

Independent laboratory for mapping, localization, route planning and safe navigation experiments. It does **not** import or control KageLink.

## Current priority: grid-first semantic mapping

The movement-first MapMaker did not produce a trustworthy world map in the real fullscreen game. PR 24 now begins from the calibrated square grid and treats every complete visible cell as an independent visual crop.

```text
capture target HWND
→ crop every calibrated square cell
→ compare with taught examples
→ classify confident matches
→ ask the player only about unknown cells
```

No unknown cell is silently assumed to be walkable or blocked.

Implemented:

- square-grid calibration saved per profile/region;
- exact target-window capture selected by title/HWND;
- one visual crop for every complete calibrated cell;
- explainable local descriptor using color, structure and edges;
- nearest-example recognition with adjustable confidence threshold;
- active teaching queue for unknown crops;
- semantic categories for walkable terrain, walls, jutsu terrain, blocking objects, transitions, danger and dynamic/ignored content;
- immediate reclassification of the full captured viewport after each taught example;
- saved PNG examples and JSON feature knowledge;
- simulator, occupancy grid, world graph, A*, frontier foundation and state machine retained as later layers;
- no keyboard or mouse output adapter.

Still intentionally blocked:

- stitching viewport classifications into persistent world coordinates;
- conflict resolution across repeated observations;
- automatic player/camera localization;
- assisted navigation against the live game;
- autonomous keyboard control;
- real replay and relocalization.

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

Inside the fullscreen game, press `F8`, return with `Alt+Tab`, align the grid and save.

## 2. Teach and classify visible cells

```powershell
.\navigation_lab\scripts\run_tile_map_maker.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -RegionId "mapping_input_calibration" `
  -Profile "default" `
  -SimilarityThreshold 0.92
```

Minimize the MapMaker, return to the game and press `F8`. After returning with `Alt+Tab`, the viewport is colored by category. Select an unknown cell and teach it; all similar cells are re-evaluated immediately.

Read [`SEMANTIC_TILE_MAPPER.md`](SEMANTIC_TILE_MAPPER.md) for the complete workflow and category definitions.

## Legacy diagnostic observer

The input/motion observer remains available for experiments, but it is no longer proof of a valid map:

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
