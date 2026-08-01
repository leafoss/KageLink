# Kage Combat Lab and `grid_focus_v2`

## Intervention status

This intervention started from:

```text
6dfa5281357eb52abec4cf37f2c080a84f987dda
```

PR #23 must remain open, Draft, and unmerged. The experimental strategy must not become the installer default before the offline gates and explicit physical validation are approved.

## Limitation of the latest capture

The latest physical-test evidence was received as:

```text
round_001_20260731_195348_6508.avi
```

The file was successfully materialized in the intervention environment, but the local video executor failed before decoding its frames. No visual conclusion about this particular recording is therefore stated as fact here. The redesign is grounded in the previously documented physical regression, the actual PR runtime, and Rafael's intervention specification.

The processed AVI remains useful for human comparison, but it is not treated as a perfect RAW deterministic replay source.

## Previous runtime audit

Before this intervention, the canonical round installed:

```text
kage_pilot_round.py
→ kage_pilot_visual_return.py
→ resolution bridges
→ historical v03k/v03j/v03i/v03h/v03g/v03e/v03 chain
→ install_combat_target_bridge
→ install_combat_runtime_hardening
→ install_runtime_guard
→ meditation, geometry, and resource bridges
→ install_runtime_lab
→ install_round_video_performance_guard
→ runtime.main
```

### Previous runtime map

| File | Class/function | Responsibility | Real base | Later replacement | Effective configuration | Identified risk |
|---|---|---|---|---|---|---|
| `kage_pilot_round.py` | `main()` | Isolated round entry | — | None | Parent-process arguments | Behavior depended on import order |
| `kage_pilot_visual_return.py` | `main()` | Bridge installation | Historical runtime | Recorder still changed `process` | Procedural order | A later bridge could replace the tested class |
| `kage_pilot_live_v03e_round.py` | `MovementAndAnchorObserver` | Combat and return position | Historical v03 observer | v03i and v03k | v03 observer config | Combat and return share old inheritance |
| `kage_pilot_live_v03i_round.py` | `MapSaveResyncObserver` | Stall/scene-spike resync | `MovementAndAnchorObserver` | v03k | `frame_gap=1.25s` | Global resync changes tracker, target, and grid |
| `kage_pilot_live_v03k_round.py` | `OpponentAwareObserver` | KO identity gate | Observer from v03j/v03i | Persistent bridge | Two KO evidence hits | Captures bases before later bridges |
| `combat_target_runtime_v351.py` | `CombatFilteredTracker` | Preliminary effect filter | Historical tracker | None | Combat JSON | Local class created during installation |
| `combat_target_runtime_v351.py` | `PersistentCombatTargetObserver` | Persistent identity | `OpponentAwareObserver` | Later hardening | 48/96 px temporal memory | Accepted rebind updated position, size, appearance, and direction at once |
| `dojo_combat_runtime_hardening_v351.py` | `PhysicallyHardenedCombatObserver` | Emergency limiting policy | Persistent observer | Recorder altered `process` | 0.9/1.2/3.0 s, score 0.62 | Another local subclass without independent spatial authority |
| `grid_target_observer_v03d.py` | `TileCalibratedGridTargetObserver` | Preliminary grid selection | Foot-anchored observer | Wrapped by the chain above | Two-frame confirmation | Parts of contact/rebind still admitted `OCCLUDED` |
| `dojo_vision_lab_v351.py` | `install_runtime_lab()` | Diagnostic AVI | Final-class monkeypatch | Last observer alteration | 2 fps | Processed recorder, not deterministic RAW replay |

### Code-proven structural cause

The runtime contained two competing geometries:

```text
logical grid and distance → foot anchor
persistent memory → track.center
```

A visual association could renew and move identity using a blob center while distance decisions used the foot cell. The emergency hardening blocked some unsafe movement, but it did not prevent internal hypothesis contamination.

## Current canonical installation

The canonical round now has one combat installation point:

```text
install_combat_strategy_runtime(runtime)
```

The old persistent and hardening installers are no longer stacked by the canonical entrypoint. Their files remain for tests, compatibility, and investigation.

Concrete runtime classes are named and reported:

```text
CanonicalCombatTracker
CanonicalCombatObserver
CanonicalCombatDecisionEngine
CanonicalCombatPlanner
CanonicalCombatVictoryWatcher
```

After all bridges finish, the process emits once:

```text
DOJO_COMBAT_RUNTIME_PROVENANCE
```

The event includes the concrete classes/modules, selected strategy, configuration path, and effective parameters.

## Explicit strategies

The factory exposes:

```text
legacy_safe
persistent_hardened
grid_focus_v2
```

`legacy_safe` is a diagnostic fallback based on immediate visible-track acquisition.

`persistent_hardened` represents the conservative emergency policy and remains the configured default until physical approval.

`grid_focus_v2` is the experimental spatial strategy:

```text
pixels
→ contour
→ foot anchor
→ logical cell
→ spatial hypothesis
→ Combat Target
```

## Spatial observation authority

Each observation reports its anchor cell, bbox-intersected cells, body-cell coverage, visibility, body quality, contamination, score, appearance, size, and classification.

Classifications are:

```text
CLEAN_SINGLE_CELL_BODY
BODY_SPANS_BORDER
MULTI_CELL_EFFECT
TARGET_EFFECT_CONTAMINATED
CAMERA_OR_SCENE_MOTION
UNKNOWN_BLOB
```

Only clean visual evidence may update confirmed/predicted cell, appearance, size, direction, positive confidence, and `last_clean_seen_at`.

Contaminated activity may update only `last_any_activity_at`, possible presence in the locked cell, and contamination diagnostics. It cannot move or renew the clean identity.

## Two-phase acquisition

A plausible clean observation first creates `ATTENTION`. It may preserve R and safe facing, but cannot authorize H, movement, or a persistent Combat Target.

`TARGET_CONFIRMED` requires two coherent clean observations in the same spatial hypothesis with a valid foot anchor, body gate approval, adequate score, no contamination, and plausible displacement.

## Perception scope after lock

```text
GLOBAL_DISCOVERY
LOCKED_CELL_FOCUS
PREDICTED_CELL_FOCUS
LOCAL_GRID_RECOVERY
GLOBAL_RECOVERY
COMBAT_DISABLED
```

After lock, distant scene candidates cannot compete for identity. Authoritative search follows the confirmed cell, one predicted adjacent cell, and then a local 3×3 neighborhood. Global recovery returns only after real clean-visual loss.

## Spatial rebind quarantine

A new `track_id` does not immediately inherit identity. Different tracks in the same cell feed one `GridRebindHypothesis`.

While pending, the main cell, direction, appearance, size, confidence, and clean hard timeout remain unchanged. Confirmation requires two coherent clean observations in the same or a physically plausible adjacent cell.

A same-track cell transition is also quarantined. One animation frame, shadow, or partially contaminated bbox therefore cannot move the identity.

## Discrete prediction and adjacency

Prediction is limited to the confirmed cell or one of its eight neighbors. Velocity is never inherited between tracks. Prediction continuity restarts for a genuinely new `combat_target_id`.

Logical adjacency uses Chebyshev distance:

```python
max(abs(dx_cells), abs(dy_cells)) <= 1
```

All eight neighboring cells are therefore local contact.

## `MELEE_LOCK`

`MELEE_LOCK` requires a current clean body in an adjacent cell. When clean authority expires:

```text
MELEE_LOCK
→ MELEE_HOLD for a minimal grace period
→ LOCAL_GRID_RECOVERY
```

Memory alone cannot authorize movement or H.

## Own-attack effects

When H is authorized, the planner creates an `AttackVisualContext` containing origin, direction, expected corridor, and expiration. Observations in that corridor may be classified as contaminated and cannot acquire or rebind identity.

## Combat termination

After accepted KO:

```text
combat_phase = POST_COMBAT
perception_scope = COMBAT_DISABLED
Combat Target = None
pending rebind = None
attention = None
track creation = disabled
movement authority = false
attack authority = false
```

No post-KO blob can create a new target.

## Kage Combat Lab

The independent package lives at:

```text
pc_agent/kage_pilot/combat_lab/
```

It imports and sends no BYOND, keyboard, or mouse input. It contains a logical grid simulator, three-strategy comparison, deterministic JSON replay, text/JSON reports, a bounded asynchronous RAW black box, and an offline CLI.

```powershell
python -m pc_agent.kage_pilot.combat_lab --strategy grid_focus_v2 --json combat-report.json --text combat-report.txt
```

The suite covers 25 deterministic scenarios: cardinal and diagonal positions, stationary/crossing/overlap, short and long loss, horizontal and multicell effects, false nearby blobs, same-cell and impossible track changes, multiple candidates, camera shift, knockback, KO, post-KO blobs, and a second opponent after real loss.

## RAW black box

The black box is opt-in:

```text
KAGELINK_COMBAT_BLACK_BOX=1
```

It buffers RAW arena frames, timestamps, cells, candidates, tracks, observations, target snapshot, decision, command, attack context, and KO state. Rendering and video encoding do not occur in the critical loop.

It materializes only on round failure, explicit `KAGELINK_COMBAT_BLACK_BOX_MATERIALIZE=1`, or an explicit debug request, producing:

```text
raw_arena_frames.npz
replay.json
```

## Offline release gate

`test_combat_lab_release_gate_v351.py` requires:

```text
all grid_focus_v2 scenarios = PASS
false_rebinds = 0
multi_cell_blobs_promoted = 0
post_ko_targets = 0
time_in_melee_lock_without_clean_visual = 0
prediction_cell_jumps = 0
deterministic replay
configured default remains persistent_hardened
all three strategies remain comparable
```

CI results and consolidated metrics are recorded after the head stabilizes.

## Future physical gate

Even after offline approval, `grid_focus_v2` must not automatically become the default. A real Windows/BYOND test must confirm one logical target per opponent, no multicell promotion, no post-KO target, no prolonged visionless melee lock, no direction change from pending rebind, no multicell prediction jump, visible local focus after lock, and global recovery only after real loss.

CI proves logical consistency, compilation, and packaging. It does not replace physical validation.
