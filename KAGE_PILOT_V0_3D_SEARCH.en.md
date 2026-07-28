# Kage Pilot v0.3d — Concentric trainer search

v0.3d preserves the validated v0.3c combat policy and changes only the post-combat fallback used when no reliable Dojo trainer anchor exists.

## Strategy

The search starts at the cell where post-combat began and traverses complete concentric rings:

```text
complete radius 1
→ complete radius 2
→ complete radius 3
→ ...
```

On an orthogonal grid, each “circle” is represented by a Chebyshev-distance square ring. Every direction remains a short pulse; no arrow key is held.

## Initial arena model

The initial calibration uses a known arena 30 cells wide and 24 cells high. Because the starting position may be any cell, the conservative maximum search radius is 29 cells.

This size is only an initial safety boundary. The intended evolution is to infer boundaries, obstacles, and already visited areas visually, removing the dependency on manually supplied dimensions.

## Priority order

1. use the persistent trainer anchor shifted by global camera motion;
2. if no anchor exists, execute concentric cell-ring search;
3. stop the search as soon as the trainer is visually recognized;
4. use memory only for navigation;
5. require visual confirmation and adjacency before tapping `V`.

## Safety

- `R` and `H` remain off during post-combat;
- arrows are short pulses only;
- `V` remains a toggle: one tap enters meditation and another exits;
- `F12` releases all keys and stops immediately;
- v0.3c remains available as the validated fallback version.
