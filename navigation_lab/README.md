# Kage Navigation Lab — PR 24

Independent laboratory for mapping, localization, route planning and safe navigation experiments. It does **not** import or control KageLink.

## Current priority: mapping first

The live Observer Mode is the active PR 24 milestone. Real navigation remains blocked until the program can build, save and restore a trustworthy relative map from the game window.

The default mapper now follows this rule:

```text
one movement-key tap = one attempted logical cell
visible movement = visited cell
no visible movement before timeout = blocked cell
```

The configured `64x64` size represents the logical tile and debug grid. The camera does not need to scroll a full 64 pixels to confirm each step.

Implemented and automatically validated:

- visible Windows client capture selected by window title;
- passive global observation of arrow keys and WASD;
- movement keys accepted only while the game is foreground;
- comparison between the pre-input frame and subsequent frames;
- directional screen-motion confirmation for following/hybrid cameras;
- exactly one logical tile per physical key tap;
- automatic `#` marking when an attempted move produces no visual translation;
- unbounded sparse map of visited and blocked cells;
- ASCII projection centered on the current position;
- automatic start, minimization behind fullscreen and save after every resolved attempt;
- atomic save and automatic restore per profile/region;
- original and processed capture panels for later inspection;
- occupancy grid, world graph, A*, frontier foundation and simulator scenarios;
- PowerShell setup, observer, simulator, test and diagnostics scripts;
- isolated Windows CI workflow.

Still intentionally blocked:

- automatic extraction of all visible walkable ground;
- Teaching Mode labels and landmark capture;
- player tracking for a fully fixed camera;
- assisted navigation against the live game;
- autonomous keyboard control;
- replay of real captured sessions.

The observer only listens. It never sends or suppresses game input. `--arm-input` has no effect.

## Requirements

- Windows 10 or later;
- Python 3.11 or later;
- Tkinter included in the Python installation;
- the game client visible and not minimized for the first capture backend.

## Setup

```powershell
.\navigation_lab\scripts\setup_navigation.ps1
```

## Start fullscreen mapping

```powershell
.\navigation_lab\scripts\run_mapping_observer.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -RegionId "mapping_calibration" `
  -TileSize 64 `
  -Fps 12 `
  -CameraMode following `
  -MappingStrategy input `
  -CommandTimeout 0.70 `
  -MinCommandShift 2.0 `
  -NewMap
```

The window starts automatically and minimizes. Return to the fullscreen game and tap one direction at a time. After the test, Alt+Tab back to inspect the ASCII map and event log.

Expected events:

```text
MOVED RIGHT -> cell=(1,0)
BLOCKED RIGHT -> obstacle=(1,0)
```

Map symbols:

```text
P current position
, visited cell
# blocked attempted cell
? unknown cell
```

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
