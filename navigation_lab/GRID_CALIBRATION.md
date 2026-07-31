# Grid Calibration Lab

The Grid Calibration Lab creates one saved square-grid definition for a mapping profile and region before live mapping begins.

## Why it uses a frozen frame

`Shinobi Story Online` may need to remain foreground in fullscreen. The calibration tool therefore does not require its editor window to cover the game.

1. Start the calibration tool.
2. Minimize it.
3. Return to the fullscreen game.
4. Press `F8` while the game is foreground.
5. Return with `Alt+Tab`.
6. Adjust the grid over the frozen game frame.

The `F8` listener is passive. It does not send, suppress or replace any input.

## Adjustable values

- square cell size in pixels;
- horizontal grid offset;
- vertical grid offset;
- line thickness;
- line opacity.

Clicking the frozen image anchors a grid intersection to the selected image point. The center button places an intersection on the capture center.

## Run

```powershell
.\navigation_lab\scripts\run_grid_calibration.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -RegionId "mapping_input_calibration" `
  -Profile "default"
```

The calibration is stored under:

```text
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>\calibrations\<region>_grid.json
```

## Mapping integration

The Mapping Lab automatically loads the saved calibration when the same `Profile` and `RegionId` are used. The saved cell size replaces the command-line default and the processed preview uses the saved offsets, thickness and opacity.

Use `--ignore-grid-calibration` only for diagnostics when a saved calibration must be bypassed.

## Physical approval

A calibration is ready when:

- each visual tile is covered by one square;
- vertical and horizontal lines remain equally spaced;
- the same grid fits multiple nearby positions in the region;
- the chosen intersection offset stays aligned after a fresh capture;
- reopening the tool restores the saved values.
