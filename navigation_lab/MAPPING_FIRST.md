# Mapping First — live 64 px tile observer

PR 24 now treats mapping as the gate before real navigation. The simulator and A* planner remain available, but live assisted/autonomous navigation stays blocked until this mapping layer is physically validated.

## What this milestone does

- locates the visible Windows client area whose title contains `Shinobi Story Online`;
- captures only that client rectangle at a configurable FPS;
- estimates translational screen motion between consecutive frames with phase correlation;
- converts screen displacement into inverse world displacement;
- accumulates partial pixel displacement instead of rounding every frame;
- advances the relative map only after the accumulated displacement reaches one configurable tile;
- uses `64x64` pixels as the default tile size;
- stores visited cells in an unbounded sparse map centered at `(0, 0)`;
- displays original capture, processed capture, 64 px grid, motion vector, residual and ASCII map;
- saves the mapping state atomically under the selected profile and region;
- restores an existing map automatically unless `-NewMap` is supplied;
- never sends keyboard or mouse input.

## Important limitation of the first capture backend

The initial backend captures the visible client rectangle associated with the HWND. The game must not be minimized and its client area must not be covered by another window. A future Windows Graphics Capture backend can replace this without changing the motion or tile-mapping engine.

## Coordinate rule

When a following camera moves the scenery left, the character moved right in world space:

```text
world movement = inverse(screen movement)
```

Partial motion is retained:

```text
-16 px screen X, repeated four times
= +64 px world X
= +1 map tile when tile size is 64 px
```

The `-InvertX` and `-InvertY` switches exist for physical calibration if the game/capture convention produces an inverted axis.

## First physical test

Keep the game visible and place the debug window beside it rather than over it.

1. Stand in a safe location.
2. Start the observer.
3. Click **Start / Iniciar**.
4. Do not move for several seconds. The map should remain at `(0, 0)`.
5. Walk right until the background visibly scrolls by approximately one cell.
6. Confirm the map becomes `(1, 0)`.
7. Walk down, left and up to form a square.
8. Confirm the map returns close to `(0, 0)` and the ASCII trail forms a loop.
9. Click **Save / Salvar**, close and reopen with the same `RegionId`.
10. Confirm the previous map and position are restored.

## Run

```powershell
.\navigation_lab\scripts\run_mapping_observer.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -RegionId "mapping_calibration" `
  -TileSize 64 `
  -Fps 10 `
  -CameraMode following
```

Use a clean map when required:

```powershell
.\navigation_lab\scripts\run_mapping_observer.ps1 `
  -RegionId "mapping_calibration" `
  -TileSize 64 `
  -NewMap
```

## Approval gate before obstacle mapping

This milestone is approved only after physical evidence shows:

- no drift while standing still;
- horizontal and vertical screen shifts have the correct map direction;
- four 16 px partial movements accumulate into one 64 px cell;
- a square route produces a recognizable loop;
- save, restart and restore preserve the map;
- loss of focus, minimization or missing window produces a visible error rather than invented movement.
