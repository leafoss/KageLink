# Testing and approval evidence

## Automated suite

Run:

```powershell
.\navigation_lab\scripts\run_tests.ps1
```

The suite validates:

- grid observation and serialization;
- world graph reliable-route selection;
- JSON persistence;
- A* obstacle avoidance and no-route detection;
- frontier selection;
- legal and illegal state transitions;
- all sixteen required simulator scenarios;
- dynamic obstacle replanning;
- landmark-based confidence restoration;
- synthetic horizontal and vertical screen translation;
- one movement-key tap creating exactly one logical tile;
- an 8 px visual response confirming one 64 px logical tile;
- absence of motion after a key marking the attempted neighbor blocked;
- sideways animation not confirming the wrong movement direction;
- sparse-map export and restoration.

## Fullscreen physical mapping test

Run:

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

The observer starts automatically and minimizes. Return to the fullscreen game.

### Successful step

Tap RIGHT once in an open direction. After returning to the Mapping Lab, the event log should contain:

```text
ATTEMPT RIGHT: waiting for visible movement
MOVED RIGHT -> cell=(1,0)
```

The ASCII map must gain one visited cell `,`, and `P` must move exactly one column.

### Blocked step

Stand beside a wall and tap toward it once. Expected event:

```text
BLOCKED RIGHT -> obstacle=(1,0)
```

`P` must remain in its previous cell and `#` must appear in the attempted neighboring cell.

### Square route

Tap one cell at a time:

```text
RIGHT
DOWN
LEFT
UP
```

Expected final position:

```text
(0,0)
```

### Focus safety

Keys pressed while the Mapping Lab, PowerShell or another application is foreground must be ignored and must not change the map.

### Persistence

Close the observer and run the same command without `-NewMap`. The same visited and blocked cells must return.

## Required simulator scenarios

1. `01_basic_corridor`
2. `02_multiple_paths`
3. `03_blocked_shortest_path`
4. `04_unknown_world`
5. `05_landmark_relocalization`
6. `06_region_transition`
7. `07_false_transition`
8. `08_stuck_in_corner`
9. `09_input_without_movement`
10. `10_movement_without_expected_input`
11. `11_lost_position`
12. `12_route_replanning`
13. `13_loop_prevention`
14. `14_destination_confirmation`
15. `15_partial_map`
16. `16_dynamic_temporary_obstacle`

## Physical gate still required

No claim of real-game navigation approval is allowed until Windows/BYOND evidence also covers:

- accurate input-confirmed mapping in multiple real regions;
- collision versus lag versus lost focus;
- player tracking when the camera does not scroll;
- teaching annotations;
- landmark dataset creation;
- replay from real frames and timestamps;
- input arming and emergency release;
- no-progress and stuck recovery;
- arrival confirmation in at least two real regions.

Every physical bug must become a recording or deterministic regression fixture before correction.
