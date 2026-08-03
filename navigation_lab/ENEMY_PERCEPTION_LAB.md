# Enemy Perception Lab / Laboratório de Percepção de Inimigos

## Status

Experimental, passive and auditable. This laboratory observes the `Shinobi Story Online` HWND and never sends keyboard or mouse input. It is based on PR 24 and must not be merged independently while `feat/pr24-navigation-system` is not part of `main`.

## Goal

```text
capture HWND
→ split the calibrated frame into 64 px cells
→ compare each current cell with known empty references
→ detect relevant overlays
→ merge overlay components across adjacent cells
→ classify the isolated entity or group it as unknown
→ associate it with a Track ID
→ measure its own movement and distance to Player
→ accumulate explainable hostility evidence
→ mark possible, probable or confirmed hostility
```

The system deliberately separates:

- terrain classification from entity classification;
- visual class evidence from observed behavioral evidence;
- global camera movement from an entity moving between world cells;
- a possible enemy from a confirmed enemy.

## Architecture

```text
ContinuousSemanticMapper (PR 24)
        ↓
BackgroundReferenceStore
        ↓
OverlayDetector
        ↓
EntityExtractor
        ↓
EntityFeatureExtractor + EntityKnowledgeBase
        ↓
EntityTracker
        ↓
HostilityAnalyzer
        ↓
DebugRecorder + EnemyPerceptionWindow
```

Modules live under `navigation_lab/enemy_perception/`.

## Empty background policy

A world cell is not learned as empty from one frame. A new reference requires repeated, visually stable observations and a confirmed terrain classification. Player cells, moving frames, unknown terrain and low-confidence terrain are not eligible.

Up to four references can be retained for one world coordinate, allowing animated terrain to choose the closest known empty frame before subtraction.

## Overlay processing

The first implementation intentionally uses light processing suitable for pixel art:

1. absolute BGR difference;
2. maximum channel intensity;
3. configurable pixel threshold;
4. small morphological opening;
5. connected components;
6. minimum component area and changed-pixel ratio.

No neural detector is required for the initial physical validation.

## Multi-cell entities

Overlay masks are projected back to the full game frame. Components touching or separated by a small configurable gap are joined globally, including across tile boundaries. The lower center of the resulting bounding box is used as the preferred feet/anchor cell.

## Confidence policy

```text
confidence >= 0.95          confirmed visual classification
0.90 <= confidence < 0.95  provisional visual classification
confidence < 0.90           UNKNOWN_ENTITY group
```

Unknown entities are saved and grouped by masked visual similarity. Their knowledge is stored separately from PR 24 terrain examples.

## Tracking

Each entity receives an identifier such as `ENT-000042`. Association uses:

- current or neighboring world cell;
- masked visual similarity;
- recent active tracks;
- configurable TTL before expiration.

The tracker stores previous and current world positions, position history, movement count, stationary observations and classification evidence.

## Hostility states

```text
UNKNOWN_VISUAL
STATIC_OVERLAY
MOBILE_ENTITY
APPROACHING_ENTITY
FOLLOWING_ENTITY
HOSTILE_PROBABLE
HOSTILE_CONFIRMED
```

Initial score evidence:

```text
+1 entity moved by itself
+2 distance decreased by entity movement
+2 repeated approach
+3 approach while Player was stationary
+4 route correction while still approaching
+5 known attack animation evidence
+8 HP loss correlated with the nearby entity
```

A single approach never confirms an enemy. A visual `ENEMY` example contributes evidence but does not immediately produce `HOSTILE_CONFIRMED`. Confirmation requires score 16 or combined attack and HP-loss evidence.

## Frame-by-frame debug output

When `-DebugFrames` is enabled, every processed frame is recorded, including empty frames, moving-camera frames, frames without Player, frames without a background reference and frames without entities.

```text
%LOCALAPPDATA%\KageNavigationLab\profiles\<profile>\enemy_perception_debug\<session_id>\
  session.json
  events.jsonl
  tracks.json
  summary.csv
  errors.log
  frames\frame_000001\
    00_raw_window.png
    01_grid_overlay.png
    02_background_composite.png
    03_difference_composite.png
    04_mask_composite.png
    05_components_overlay.png
    06_entities_overlay.png
    07_tracking_overlay.png
    08_hostility_overlay.png
    frame.json
    entities\
      ENT-000001_crop.png
      ENT-000001_mask.png
      ENT-000001_difference.png
      ENT-000001.json
```

`frame.json` records window metadata, calibration, camera movement, Player position, every cell decision, selected background reference, difference metrics, extracted entities, Track IDs, distance history, hostility changes and errors.

## Run

```powershell
.\navigation_lab\scripts\run_enemy_perception_lab.ps1 `
  -WindowTitle "Shinobi Story Online" `
  -Profile "default" `
  -RegionId "mapping_input_calibration" `
  -CaptureInterval 0.20 `
  -AutoThreshold 0.95 `
  -ReviewThreshold 0.90 `
  -OverlayPixelThreshold 24 `
  -MinChangedPixelRatio 0.03 `
  -MinComponentArea 12 `
  -TrackTtlFrames 10 `
  -DebugFrames `
  -KeepWindowVisible `
  -SessionName "enemy_detection_physical_test_01"
```

Prerequisites for the same profile and region:

1. saved 64 px grid calibration;
2. taught PR 24 tile knowledge containing Player and representative terrain;
3. game window visible and capturable by the existing HWND backend.

## Automated validation

`navigation_lab/tests/test_enemy_perception_lab.py` contains 47 deterministic tests covering:

- empty and animated background references;
- overlay masks and noise rejection;
- multi-cell component joining and feet anchoring;
- masked feature extraction and unknown grouping;
- Track ID continuity, crossing and expiry;
- Player movement versus entity movement;
- repeated approach, decay and attack/HP evidence;
- all mandatory per-frame debug files and session summary.

Run:

```powershell
python -m unittest navigation_lab.tests.test_enemy_perception_lab -v
```

## Physical approval gate

Before any combat integration, validate in the real game that:

1. the 64 px grid remains aligned;
2. empty terrain does not create entities;
3. animated terrain selects a valid empty reference;
4. a character over terrain produces a meaningful mask;
5. head, body and feet become one entity;
6. the same character keeps one Track ID while moving;
7. camera scroll is not interpreted as entity motion;
8. Player movement toward a static NPC does not become pursuit;
9. an entity approaching a stationary Player accumulates evidence;
10. every interpretation can be reconstructed from the debug session.

## Known limits

- Physical thresholds still require calibration against real BYOND frames.
- A fully stationary hostile entity remains visual evidence until behavior or attack evidence appears.
- Multiple visually identical entities crossing can still cause ambiguous assignment.
- Attack and HP-loss inputs are supported by the analyzer but are not yet wired to combat/HUD modules in this passive branch.
- Teleports, death, region transitions and long-session localization drift inherit the current PR 24 limitations.

## Safety boundary

This branch must remain draft. It does not navigate, attack, suppress input or control the game. It produces evidence for later physical review only.
