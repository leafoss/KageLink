# Kage Navigation Lab — PR 24

Independent laboratory for mapping, localization, route planning and safe navigation experiments. It does **not** import or control KageLink.

## Current priority: mapping first

The live Observer Mode is now the active PR 24 milestone. Real navigation remains blocked until the program can build, save and restore a trustworthy relative map from the game window.

Implemented and automatically validated:

- visible Windows client capture selected by window title;
- original and processed live capture panels;
- translational screen-motion estimation with correlation confidence;
- configurable tile odometry with `64x64` pixels as the default cell size;
- accumulation of partial movement before a tile transition;
- inverse screen-to-world movement conversion for a following camera;
- unbounded sparse map of visited cells;
- ASCII mapping projection centered on the current position;
- atomic save and automatic restore per profile/region;
- controls for pause, reset and save;
- occupancy grid, world graph, A*, frontier foundation and simulator scenarios;
- PowerShell setup, observer, simulator, test and diagnostics scripts;
- isolated Windows CI workflow.

Still intentionally blocked:

- Teaching Mode labels and landmark capture;
- automatic obstacle extraction;
- player tracking for a fully fixed camera;
- assisted navigation against the live game;
- autonomous keyboard control;
- replay of real captured sessions.

No live mode sends input. `--arm-input` has no effect.

## Requirements

- Windows 10 or later;
- Python 3.11 or later;
- Tkinter included in the Python installation;
- the game client visible and not minimized for the first capture backend.

## Setup

```powershell
.\navigation_lab\scripts\setup_navigation.ps1
```

## Start live mapping with 64 px cells

```powershell
.\navigation_lab\scripts\run_mapping_observer.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -RegionId "mapping_calibration" `
  -TileSize 64 `
  -Fps 10 `
  -CameraMode following
```

Keep the game client unobstructed. Place the Mapping Lab window beside the game, then click **Start / Iniciar** and walk manually.

The interface shows:

- original game client;
- processed frame with a 64 px grid and motion vector;
- detected screen displacement and correlation;
- pixel residual not yet large enough to become a cell;
- current relative tile coordinate;
- visited-cell ASCII map;
- save and reset controls.

Read the complete physical procedure in [`MAPPING_FIRST.md`](MAPPING_FIRST.md).

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

Windows data is stored by default under:

```text
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>
```
