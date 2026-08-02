# Mapping First — fullscreen input-confirmed tile mapper

PR 24 treats mapping as the gate before real navigation. The simulator and A* planner remain available, but live assisted/autonomous navigation stays blocked until this mapping layer is physically validated.

## Mapping rule

The default strategy is now **input-confirmed mapping**:

```text
one physical movement-key tap
→ one attempted logical map cell
→ visible screen movement confirms passage
→ no visible movement within the timeout marks the attempted neighbor as blocked
```

The configured `64x64` size describes the logical game tile and the debug grid. The camera is **not** required to move a full 64 pixels for each accepted step. An 8 px or 20 px scrolling response can confirm one logical tile when it follows the expected direction.

## What this milestone does

- locates the visible Windows client whose title contains `Shinobi Story Online`;
- captures its visible client rectangle at a configurable FPS;
- passively listens for arrow keys and WASD without suppressing or sending input;
- ignores movement keys unless the game window is the foreground window;
- compares the frame before the key with subsequent frames;
- confirms one logical cell when screen translation matches the key direction;
- marks the attempted neighbor as `#` when no matching movement appears before timeout;
- uses `64x64` pixels as the default logical cell size;
- stores visited and blocked cells in an unbounded sparse map centered at `(0, 0)`;
- auto-starts, minimizes behind the fullscreen game and auto-saves after each resolved attempt;
- restores an existing map automatically unless `-NewMap` is supplied;
- never sends keyboard or mouse input.

## Fullscreen workflow

The Mapping Lab does not need to remain visible or over the game.

1. Open `Shinobi Story Online`.
2. Run the observer command.
3. The Mapping Lab starts automatically and minimizes.
4. Return to the fullscreen game.
5. Tap one movement key at a time during calibration.
6. After the route, use Alt+Tab to inspect the map and event log.

A held key is intentionally counted as one attempt until released. During the first calibration, use distinct taps rather than holding a direction continuously.

## Coordinate and confirmation rule

For a following camera:

```text
RIGHT input expects scenery movement LEFT
LEFT input expects scenery movement RIGHT
DOWN input expects scenery movement UP
UP input expects scenery movement DOWN
```

The default confirmation window is `0.70 s`, and the default minimum projected screen shift is `2 px`.

Successful attempt:

```text
MOVED RIGHT -> cell=(1,0)
```

Blocked attempt:

```text
BLOCKED RIGHT -> obstacle=(1,0)
```

Map symbols:

```text
P = current position
, = visited cell
# = blocked attempted cell
? = unknown cell
```

## Run

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

Use the same command without `-NewMap` to restore the saved map.

For diagnostics only, the previous free-running odometry remains available with:

```powershell
-MappingStrategy continuous
```

It is not the default mapping method.

## First physical validation

Use a safe area and tap:

```text
RIGHT
DOWN
LEFT
UP
```

Expected result:

- each successful tap changes the map by exactly one cell;
- returning around the square reaches `(0,0)`;
- tapping toward a wall leaves `P` in place and adds `#` beside it;
- unrelated animation does not create movement without a recorded movement key;
- keys pressed while the game is not foreground are ignored;
- closing and reopening without `-NewMap` restores visited and blocked cells.

## Current limitation

This confirmation model assumes a following or hybrid camera that visibly scrolls in response to movement. A fully fixed camera requires player-sprite tracking, which is a later mapping milestone. Automatic extraction of all visible walkable ground and obstacles is also not implemented yet; the current map learns from successful and failed movement attempts.
