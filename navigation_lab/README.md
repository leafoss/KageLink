# Kage Navigation Lab — PR 24

Independent laboratory for mapping, localization, route planning and safe navigation experiments. It does **not** import or control KageLink.

## Current milestone

Implemented and automatically validated:

- occupancy grid with confidence and observations;
- world graph with reliable-route weighting;
- A* local planning;
- frontier selection foundation;
- explicit navigation state machine;
- JSON persistence under a profile directory;
- sixteen deterministic simulator scenarios;
- route replanning after temporary obstacles;
- simulated loss and recovery of localization;
- bilingual desktop debug window built with Tkinter;
- PowerShell setup, execution, tests and diagnostics scripts;
- isolated Windows CI workflow.

Intentionally blocked until physical Windows/BYOND validation:

- Observer Mode against the live game;
- Teaching Mode against the live game;
- Assisted Navigation against the live game;
- autonomous keyboard control;
- landmark template capture from real frames;
- window-specific image capture and replay of real sessions.

The application returns exit code `3` if one of those modes is requested. It never silently sends input.

## Requirements

- Windows 10 or later for the intended local workflow;
- Python 3.11 or later;
- Tkinter included in the Python installation for the debug window.

## Setup

From the repository root:

```powershell
.\navigation_lab\scripts\setup_navigation.ps1
```

## Run the desktop simulator

```powershell
.\navigation_lab\scripts\run_simulator.ps1 `
  -Scenario 12_route_replanning `
  -Language pt-BR `
  -DebugWindow
```

The window shows the map, current state, estimated and actual position, action, reason, confidence, recovery count and event stream.

## Run without the window

```powershell
.\.venv-navigation\Scripts\python.exe -m navigation_lab `
  --mode simulator `
  --scenario 05_landmark_relocalization `
  --json
```

## List scenarios

```powershell
.\.venv-navigation\Scripts\python.exe -m navigation_lab --list-scenarios
```

## Record a simulated session

```powershell
.\navigation_lab\scripts\run_simulator.ps1 `
  -Scenario 03_blocked_shortest_path `
  -RecordSession
```

By default, Windows data is stored in:

```text
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>
```

## Test

```powershell
.\navigation_lab\scripts\run_tests.ps1
```

## Safety rule

The first milestone has no keyboard input adapter. `--arm-input` is parsed for future compatibility but has no effect in simulator mode. Live modes are blocked until physical validation creates reproducible evidence and regression tests.
