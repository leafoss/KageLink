# Desktop debug window

Run:

```powershell
.\navigation_lab\scripts\run_simulator.ps1 -Scenario basic_world -DebugWindow
```

The current simulator window contains:

- application, state and step header;
- resizable ASCII/local map panel;
- state and pose telemetry;
- actual versus estimated position;
- localization and route confidence;
- current action and reason;
- recovery counter;
- append-only decision and event timeline.

## Planned live panels

The physical Windows phase must add, without removing current telemetry:

- original target-window frame;
- processed frame with overlays;
- player candidate and movement vectors;
- obstacle candidates;
- landmark candidates;
- suspected transitions;
- capture and processing FPS;
- frame latency and dropped frames;
- focus, arming and emergency-stop state.

No placeholder panel may claim that live capture is active when it is not.
