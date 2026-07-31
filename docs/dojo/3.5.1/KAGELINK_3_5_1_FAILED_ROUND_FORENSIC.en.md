# KageLink 3.5.1 — forensic review of the first physical defeat

## Status

This review records a **severe physical regression** observed in:

```text
round_001_20260731_184428_19600.avi
```

The diagnostic video contains 106 frames at 2 fps, 1280×720, and approximately 53 seconds.

Passing automated tests before this capture did not prove that the physical behavior was correct. The round was lost and the previous fix cannot be considered approved.

## Important grid correction

The first visual inspection suggested a cell size close to 72 pixels. Raw-frame measurement and runtime review corrected that interpretation:

```text
logical mode: 64
effective cell_size: 64 px
Trainer PNG: 72×73 px
```

The 72×73 PNG is used only for raw visual Trainer matching. It does not define navigation geometry.

The actual grid defect was its **anchor point**:

```text
before: visual sprite center
correct: map cell under the character's feet
```

A sprite center can sit roughly half a cell above the occupied floor tile. This placed PLAYER and TARGET in the wrong row, causing false `d=0`/`d=1`, wrong direction, and movement or stopping at the wrong time.

## Observed timeline

### 0–4 seconds

- A logical identity was created before a reliable enemy body existed.
- State entered `OCCLUDED_PREDICTED` with very little visual evidence.
- A large vertical contour near the player was treated as contact.

### 6–16 seconds

- The same logical identity rapidly switched visual tracks.
- Tracks such as `#2` and `#7` were associated with the same engagement.
- Horizontal and vertical attack effects remained eligible.
- Recorded direction and executed command diverged, including LEFT paired with `FACE:right` and DOWN paired with `FACE:up`.

### 18–30 seconds

- Large motion-mask regions, horizontal strips and near-player effects continued creating tracks.
- Confidence remained close to 1.0 while visual identity changed.
- At about 30 seconds the target was `LOST/OCCLUDED_PREDICTED`; memory predicted a point to the player's right that did not correspond to the relevant physical contact.
- Movement mode could remain `PURSUIT`.

### 32–50 seconds

- The logical identity continued hopping through tracks such as `#3`, `#5`, `#21` and `#40`.
- Logical target age exceeded 70 seconds despite incompatible visual substitutions.
- Stale direction memory continued influencing commands.
- The player passed the useful contact area and failed to reconstruct the physical relationship with the opponent.

## Root causes

### 1. Sprite center used as geometry

Distance and direction used `player_center` and `track.center`, mixing artwork position with the occupied map tile.

### 2. Proximity granted unsafe authority

The previous correction preferred any nearby `d<=2` track, including `OCCLUDED`, without a strict body-shape requirement. A nearby effect could replace the real opponent.

### 3. Visual memory was too permissive

Rebind accepted `VISIBLE` or `OCCLUDED`, used a low threshold, required one observation, and retained identity for up to eight seconds.

### 4. Stale direction could replace current measurement

The persistent layer could overwrite same-frame direction with `last_contact_direction`, producing disagreement between `DIRECTION` and `CURRENT COMMAND`.

### 5. Pursuit without a visible body

During a short target gap, memory could emit `MOVE_<previous direction>`. This blind pursuit explains movement continuing after the player had passed the target.

### 6. Effect filtering was weakest near the player

Near-player protection allowed some large contours to survive rejection. Horizontal attacks, vertical columns, shadows and border regions could become authoritative at the most dangerous moment.

## New authority boundary

Observation, identity and control are now separated:

```text
observed contour
→ may remain visible in diagnostics
→ becomes authoritative only when VISIBLE and accepted by the body gate
→ identity may be remembered during occlusion
→ memory never authorizes translation
→ movement requires a current VISIBLE body, current geometry and matching direction
```

## Implemented corrections

### Physical grid

- PLAYER and TARGET use foot anchors.
- Track history is converted to approximate foot anchors.
- Mode 64 remains 64 px regardless of a 72×73 Trainer PNG.
- Diagnostics show `PLAYER FEET`, `TARGET FEET`, cell size, origin and calculated cells.

### Body gate

Only a `VISIBLE` track can acquire or rebind identity. The gate rejects:

- contours that are too small;
- contours that are too wide or tall;
- horizontal and vertical effects;
- excessive area;
- weak shape score;
- new acquisition at `d=0`;
- excessive overlap with the player body;
- large border regions.

### Conservative memory

- `OCCLUDED` cannot acquire or rebind identity.
- Rebind requires two consecutive visible observations.
- Minimum score is increased to 0.62.
- Total memory window is reduced to at most three seconds.
- Prediction is limited to 0.35 s in melee and 0.60 s in pursuit.
- Visual-ID changes clear artificial velocity.

### Fail-closed movement

- Missing or occluded body produces `HOLD` while R remains active.
- Predicted position never authorizes `MOVE`.
- Melee never authorizes translation.
- Pursuit requires a `VISIBLE` body seen within 0.20 s and `d>=3`.
- Each movement pulse requires re-observation and is separated by at least 0.75 s.
- Command direction must match the physical key.
- A mismatch is blocked and logged instead of executed.

## Added telemetry

```text
DOJO_COMBAT_BODY_REJECTED
DOJO_COMBAT_MOVE_BLOCKED
DOJO_COMBAT_FACE_BLOCKED
```

The diagnostic video now also displays:

```text
GRID / GRADE cell=<px> origin=<x,y> anchor=FEET
CELLS / CELULAS PLAYER=<cell> TARGET=<cell> d=<distance>
BODY GATE / CORPO accepted|rejected
PLAYER FEET
TARGET FEET
```

## Mandatory physical gate

The correction may be considered approved only after a real test confirms all of the following:

1. the 64 px grid is aligned to character feet;
2. large effects remain diagnostic tracks and never become authoritative targets;
3. no target is acquired while `OCCLUDED` or `LOST`;
4. displayed direction matches the physical pulse;
5. visual absence keeps R active and blocks movement;
6. every movement is one pulse followed by re-observation;
7. the player does not pass the enemy due to memory-based pursuit;
8. the fight ends through a real KO without losing the round.

CI verifies code integrity and packaging. It does not replace this physical gate.

PR #23 remains open, Draft, and unmerged.
