# PR 24 architecture

## Boundary

`navigation_lab` is a new top-level package that depends only on the Python standard library. It does not import KageLink, Kage Pilot, Dojo modules, Android code or remote APIs.

## Layers

```text
CLI / PowerShell
       ↓
Simulator or future capture adapter
       ↓
Perception observations
       ↓
Pose and confidence
       ↓
OccupancyGrid + WorldGraph
       ↓
A* local path + reliable world route
       ↓
State machine and decision telemetry
       ↓
ASCII / desktop debug visualization
```

## Current modules

- `models.py`: stable domain types, cell states, pose and decisions.
- `state_machine.py`: explicit states and permitted transitions.
- `mapping/grid.py`: occupancy cells, confidence, labels and persistence model.
- `mapping/world.py`: regions, connections and Dijkstra-style world route.
- `planning/astar.py`: local path planning with confidence-aware cell cost.
- `planning/frontier.py`: initial frontier exploration selection.
- `simulator/scenarios.py`: sixteen deterministic validation worlds.
- `simulator/engine.py`: closed-loop planning, movement verification, replanning and relocalization simulation.
- `storage/repository.py`: atomic JSON persistence under named profiles.
- `visualization/ascii_renderer.py`: diagnostic-only text projection.
- `visualization/debug_window.py`: desktop visualization.

## ASCII contract

ASCII is derived output. It is never the canonical map. The canonical map consists of structured cells with state, confidence, observation count and labels.

## Future adapters

The next physical phase should add interfaces instead of importing KageLink:

```python
class FrameSource(Protocol):
    def next_frame(self) -> FrameObservation | None: ...

class InputAdapter(Protocol):
    def pulse(self, action: str, duration_ms: int) -> None: ...
    def release_all_inputs(self) -> None: ...
```

The Windows capture and control implementations must remain inside PR 24 until approved. PR 25 will provide the KageLink adapter after the standalone contracts are stable.
