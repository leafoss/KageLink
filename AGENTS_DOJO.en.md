# Normative Bible — KageLink Dojo Trainer

This document is a normative extension of `AGENTS.en.md`. When rules appear to conflict, apply the more conservative rule for character safety, GitHub integrity and distribution traceability.

[Português](AGENTS_DOJO.md)

## 1. Authority and responsibility boundaries

```text
Shinobi Story Online
        ↑
Windows PC Agent — vision, decision and input authority
        ↑
Desktop / authenticated API
        ↑
Android APK — remote control and observation
```

- The Dojo engine runs only on the Windows computer that hosts the game.
- The APK never runs computer vision, keyboard input or combat logic.
- Desktop and APK use the same public service and state.
- No UI may implement a second combat rule set.

## 2. Installed runtime

The official Windows distribution must install side by side:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

- `KageLink.exe` hosts the Desktop, API and public state.
- `KagePilotDojo.exe` runs the isolated between-round loop.
- `KagePilotRound.exe` runs one isolated round.
- The official installation must not depend on installed Python or loose `.py` scripts.
- Python execution remains valid in source development for diagnostics and regression work.

## 3. Public API and authentication

Official endpoints:

```text
GET    /api/dojo/status
POST   /api/dojo/start
POST   /api/dojo/stop
GET    /api/dojo/logs/latest
GET    /api/dojo/templates
GET    /api/dojo/templates/{mode}/image
POST   /api/dojo/templates/{mode}
DELETE /api/dojo/templates/{mode}
```

All require the same KageLink Bearer Token. Status must expose at least:

```text
available
running
phase
current_round
completed_rounds
last_line
last_error
return_code
position_state
position_x
position_y
position_confidence
recent_actions
last_log
```

- Starting an already running trainer returns a conflict.
- Starting without an installed runtime fails closed.
- Starting without at least one valid user template fails closed with `DOJO_TRAINER_TEMPLATE_REQUIRED`.
- Stop must release inputs even when the engine has already finished.
- The log endpoint exposes only metadata and the latest diagnostic path; it never streams a live console.

## 4. External 32×32 and 64×64 templates — PROTECTED RULE

KageLink must not depend on a Dojo Trainer image embedded in the executable or Setup as its primary vision source.

The user may provide independent templates for:

```text
32×32 game mode
64×64 game mode
```

Permanent rules:

- images belong to the user's installation;
- they must be persisted outside `Program Files`, outside the executable and outside the PyInstaller temporary directory;
- the canonical location is `%LOCALAPPDATA%\KageLink\data\kage_pilot\templates`;
- normal update or reinstall must preserve templates;
- each mode has an independent file and metadata record;
- the detector may load both modes simultaneously and must choose only a stable visual match;
- upload must validate decoding, size limits and dimensions;
- removing one template must not remove the other;
- the installed trainer must not start without at least one valid user template;
- source-local calibration may remain only as development compatibility;
- no incompatible fallback may authorize clicking, `V`, or recovery movement.

## 5. Canonical Desktop navigation rule

The canonical KageLink Desktop sidebar order is:

```text
Overview
Memory
Connection
Dojo Trainer
Settings
```

**Settings must always be the final sidebar item.**

This is a permanent product rule, not a Dojo-screen detail. New pages must be inserted before `Settings`. UI tests or canonical constants must prevent regressions in this order.

The canonical Dojo page hierarchy is:

```text
Summary
Settings
Images
Logs
```

- `Summary` contains state, progress, compact location, controls and recent actions.
- `Settings` shows only parameters already present in the product contract.
- `Images` contains the 64×64 and 32×32 templates, in that order.
- `Logs` shows only the latest failure diagnostic and actions to open the file/folder.
- The page must be correct on its first frame; automatic maximize/minimize is forbidden as a layout fix.

## 6. Control interlock

While `running=true`:

- manual GAME controls are blocked;
- manual control activation is blocked;
- remote game-center clicking is blocked;
- chat and STATS remain independent;
- F12 remains the local emergency stop.

This prevents the APK, Desktop and autonomous agent from issuing competing commands.

## 7. Preserved Kage Pilot v0.3j contracts

- `R` is the only normally held combat key.
- arrow keys and `H` are short conditional pulses;
- `V` and `Y` are tap-only toggles and forbidden during combat;
- every victory requires an identity-gated accepted KO;
- a repeated previous-opponent KO invalidates the target and keeps combat active;
- memory never authorizes `V` without current visual confirmation;
- combat timeout stops the loop;
- every exit, error, stop and shutdown must release keys.

Changes to these contracts require a dedicated branch, regression coverage and physical in-game validation.

## 8. Per-session Dojo journal — 3.5.1 RULE

The Dojo journal is session-specific and must not pollute Kage Agent or general PC Agent logs.

Canonical location:

```text
%LOCALAPPDATA%\KageLink\logs\dojo
```

Contract:

1. session start creates UTF-8 `dojo_session_<timestamp>_<id>.active`;
2. important events receive timestamps, categories and immediate flush;
3. normal completion removes `.active` and leaves no permanent log;
4. an error converts it to `dojo_error_<timestamp>_<id>.txt`;
5. an abandoned `.active` becomes `dojo_incomplete_<timestamp>_<id>.txt` on next startup;
6. a journal write failure must never break F12, Stop or key release;
7. a full traceback is preserved for exceptions;
8. the file contains configuration, templates, phases, vision, position, return, fallback, exit code and final summary.

The Desktop shows only the latest failure, time, summary, path and buttons to open the file or directory.

## 9. Canonical visual position — PROTECTED 3.5.1 RULE

Character position must not be inferred only from sent keys. Pushes, teleports, jutsu, collisions, enemy movement and camera behavior can move the character without a KageLink command.

Authority hierarchy:

```text
1. proven accessible real game coordinates, if any
2. visual keyframe relocalization
3. continuous visual odometry
4. sent commands, only as auxiliary intent
```

Required states:

```text
KNOWN
UNCERTAIN
LOST
```

Origin `(0,0)` may only be set or reset after valid visual Trainer confirmation. It represents the world region where the Trainer was confirmed, not macro start or screen center.

Conceptual relation:

```text
world_motion = player_screen_motion - environment_screen_motion
```

Permanent rules:

- observed motion without a command updates X/Y as external displacement;
- a command without visual motion does not update X/Y;
- abrupt motion without visual continuity changes state to `LOST`;
- the system must never invent coordinates after continuity is lost;
- HUD, chat and fixed interface elements must be excluded whenever possible;
- estimates carry confidence and inconsistent values are rejected;
- pixel values are converted according to 32×32 or 64×64 cell mode.

## 10. Keyframes, relocalization and closed-loop return

While position is `KNOWN`, the engine may keep a bounded set of X/Y-associated keyframes. Saving every frame is forbidden.

Relocalization requires:

- stopped character and released keys;
- comparison against known keyframes;
- a minimum score;
- sufficient margin over the second-best candidate;
- X/Y restoration only with trustworthy evidence.

Trainer return is a closed-loop controller:

```text
stop
→ validate/relocalize position
→ calculate error to (0,0)
→ send one pulse
→ measure real motion
→ update X/Y
→ replan
→ repeat with limits
→ stationary scan at origin
→ short local search
→ existing ring search only as final fallback
```

- Historical route data may help avoid obstacles but never replaces current observed position.
- A push during return must trigger immediate replanning.
- A blocked move must not create false progress.
- Every return has timeout, step limit and no-progress detection.
- `LOST` position forbids a long vector return.
- F12 and Stop interrupt odometry, relocalization and return immediately.

## 11. Localization

Every new user-facing surface must exist in PT-BR and EN-US:

- Desktop;
- APK;
- controlled API messages;
- documentation;
- safety states and instructions.

Stable technical telemetry identifiers may remain in English for diagnostics.

## 12. Mandatory distribution gate

Before a Dojo-capable Release:

1. complete Python suite;
2. targeted Kage Pilot suite;
3. all three executables built;
4. functional `--help` for both helpers;
5. `KageLink.exe` startup smoke test;
6. Setup containing all three executables;
7. upload, persistence, deletion and reload of 32×32 and 64×64 templates;
8. normal journal, error journal and abandoned `.active` recovery validated;
9. odometry, keyframes, relocalization and return covered by tests;
10. `flutter gen-l10n`, analyze and tests;
11. release APK;
12. real installed-Setup validation;
13. real APK-to-Setup validation;
14. Rafael's explicit approval before merge.

Temporary PR artifacts do not replace the official Release. The Release is rebuilt from `main` and published under stable names:

```text
KageLink-Windows-Setup.exe
KageLink-Android.apk
SHA256SUMS.txt
```

## 13. Minimum 3.5.1 physical validation

The version cannot be marked ready only because builds passed. The installed Windows product must prove:

```text
Setup installs all 3 executables
→ Desktop opens correctly without maximize/restore
→ Settings remains the final sidebar item
→ Summary, Settings, Images and Logs tabs work
→ 32×32 and 64×64 templates persist
→ successful session leaves no error log
→ controlled error creates .txt and appears in Logs
→ run rounds in 32×32 and 64×64
→ position changes for walking and external displacement
→ lost position does not invent X/Y
→ relocalization recognizes a mapped region
→ return compensates a push and targets (0,0)
→ stationary scan precedes local/ring fallback
→ stop from Desktop
→ start from APK with synchronized status
→ GAME controls remain blocked
→ F12 stops and releases inputs
```

No merge or final publication may occur before this real gate.
