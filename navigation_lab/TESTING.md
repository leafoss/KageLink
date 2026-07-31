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
- all sixteen required scenarios;
- dynamic obstacle replanning;
- landmark-based confidence restoration.

## Required scenarios

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

No claim of real-game approval is allowed until Windows/BYOND evidence covers:

- exact target-window capture;
- player displacement estimation;
- collision versus lag versus lost focus;
- teaching annotations;
- landmark dataset creation;
- replay from real frames and timestamps;
- input arming and emergency release;
- no-progress and stuck recovery;
- arrival confirmation in at least two real regions.

Every physical bug must become a recording or deterministic regression fixture before correction.
