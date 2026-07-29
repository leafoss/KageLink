# KageLink — Development Bible

[Português](AGENTS.md) · [README](README.md) · [Kage Pilot](KAGE_PILOT.en.md) · [Interpreter](AGENTS_INTERPRETER.en.md)

This file is the **operational source of truth for every person or AI agent changing KageLink**.

## 1. Official source

Canonical repository:

```text
https://github.com/leafoss/KageLink
```

**GitHub is the only official source of code.**

Do not treat these as primary sources:

- old ZIP files;
- Desktop copies;
- isolated EXE/APK files;
- local installations;
- files pasted into conversations;
- uncommitted folders.

Mandatory flow:

```text
main
→ work branch
→ smallest sufficient change
→ tests
→ diff review
→ Pull Request
→ real-world validation when required
→ merge
```

## 2. Official version

The editable version source is:

```text
RELEASE_VERSION
```

The current version is **3.4.2**.

CI and release must keep these aligned:

- `RELEASE_VERSION`;
- `pubspec.yaml`;
- Inno Setup;
- backend `/api/health`;
- version labels;
- artifact names;
- READMEs;
- workflows.

Do not maintain manually edited version numbers in multiple files when the canonical source can be read or used to generate them.

## 3. Core philosophy

**Do not break working behavior.**

Every change must be:

- traceable;
- reversible;
- testable;
- limited to scope;
- compatible with unrelated modules.

Do not perform aesthetic refactors, dependency swaps, protocol changes, destructive cleanup, or incidental reorganization without an explicit request.

When Rafael authorizes reorganization, it must include an inventory, reference updates, tests, and Git rollback.

## 4. Official architecture

Main products:

1. Flutter Android application;
2. Windows/Python PC Agent;
3. Windows installer;
4. optional LeafOS integration;
5. local experimental Kage Pilot.

### 4.1 Packaged runtime

The official executable is composed through:

```text
KageLink.spec
→ unified_entry.py
→ unified_launcher.py
→ kagelink_launcher.py
→ unified_app.py
→ app.py
```

This route includes inheritance, module replacement, and runtime Interpreter selection.

Before changing the PC Agent, identify:

1. the packaged entry point;
2. the class actually instantiated;
3. the backend actually imported;
4. applicable monkeypatch/replacement behavior;
5. a test that follows the same route;
6. compatibility-only files.

A fix applied only to a layer unused by the executable is not complete.

## 5. One canonical source per responsibility

General rule:

```text
one responsibility
→ one canonical module
→ consumers reuse that module
```

Historical versions belong in Git, not active files such as:

```text
final2.py
v03l.py
hotfix_new.py
copy.py
```

Temporary compatibility must be small, explicitly marked, and have a removal plan.

### Kage Pilot

Canonical public surface:

```text
KageLink Installer/pc_agent/kage_pilot.py
```

Dojo command:

```powershell
python kage_pilot.py dojo
```

Normative documentation:

```text
KAGE_PILOT.md
KAGE_PILOT.en.md
```

Workflow:

```text
.github/workflows/kage-pilot.yml
```

New Pilot behavior must not create another versioned entry point. Internal modules use responsibility-based names.

## 6. OOC / IC contract — PROTECTED RULE

### IC blocks

Every block starting with `(*` and ending at the next `*)` is IC/RP. Fragmented blocks remain pending until closure.

### IC dialogue

The official marker is literal and case-sensitive:

```text
Says:
```

IC:

```text
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

Does not activate the rule:

```text
says:
SAYS:
sAyS:
Says Hello
```

Do not make `Says:` case-insensitive without a new explicit decision.

The rule must remain aligned across parser, tests, history, speaker extraction, RAW, READMEs, and Bibles.

## 7. OOC / IC sending

Dedicated endpoints:

```text
/api/send/ooc
/api/send/ic
```

`/api/send` is compatibility.

The Agent must:

1. receive an explicit channel;
2. focus/revalidate the game;
3. re-locate controls;
4. select only the requested field;
5. reject when unavailable;
6. never silently use the other channel.

One HWND must not represent OOC and IC simultaneously.

## 8. History and evidence identity

Preserve:

- IDs;
- timestamps;
- direction;
- channel;
- parser state;
- resynchronization;
- RAW cursor;
- character history.

IDs are identity, not disposable ordering.

New IDs must be greater than every ID already present in SQLite, RAW, Processor, or Vault. Reinstallation must not restart IDs below `last_processed_id`.

Do not delete the history database as a default fix.

## 9. LeafOS

Integration is disabled by default.

Protected flow:

```text
classified history
→ immutable RAW
→ deterministic Processor
→ closed session
→ Interpreter
→ pending_review
→ Memory Reviewer
→ human approval
→ Canonical Memory
```

Permanent rules:

- RAW is append-only;
- channel comes from the canonical parser;
- Processor does not reprocess IDs;
- Interpreter produces candidates;
- Reviewer is the human gate;
- evidence traces back to RAW;
- `memory.json` is canonical;
- `MEMORY.md` is regenerable;
- LeafOS failure does not stop chat/GAME/STATS/tunnel.

For Interpreter/Reviewer work, also read `AGENTS_INTERPRETER.md` or `.en.md`.

## 10. Persisted-state integrity

Every state must declare a policy.

### Fail closed

Use for:

- RAW;
- closed sessions;
- Reviewer state;
- Canonical Memory;
- evidence cursors;
- character identity;
- state whose loss could duplicate or misattribute evidence.

An existing invalid file must not silently become empty state.

### Quarantine and rebuild

Only for cache/checkpoint state proven reconstructible from intact sources. Preserve the invalid file and log the reason.

### Backup and defaults

Allowed for recoverable configuration, with a backup and explicit warning.

State writes should use a temporary file plus atomic replacement.

## 11. GAME and STATS

GAME remains isolated from chat, LeafOS, and STATS.

GAME contract:

```text
window: Shinobi Story Online
JPEG: 960 × 540
quality: 70
target: ~10 FPS
audio: none
modes: full | zoom
```

STATS:

```text
title: Status | Inventory
class: #32770
target: 5 FPS
clicks: left | right
```

STATS validates same game PID, title, class, visibility, last-frame HWND, and normalized coordinates.

No module becomes general desktop control.

## 12. Mandatory window/input gate

Before a click, key-down, text write, or fallback capture:

1. locate the target again;
2. validate HWND;
3. validate title and class;
4. validate PID/process;
5. validate root/child relationship;
6. validate visibility;
7. reject minimized state;
8. confirm foreground when required;
9. revalidate immediately before input;
10. verify coordinates are inside the client;
11. execute;
12. guarantee mouse-up/key-up and cleanup.

Never trust an old-frame HWND or stale coordinates blindly.

Generic screen capture is allowed only after locating, focusing, and revalidating the exact game window, preventing capture of an overlapping application.

## 13. Keys and control

Android banks:

```text
ABCD
ZXVU
```

The key whitelist is a safety contract. Do not expand it incidentally.

- release keys on deactivation;
- release on error/disconnect;
- release after foreground loss;
- key-up before key-down when changing diagonals;
- never turn KageLink into a generic command executor.

## 14. Failures and retries

Operational outcomes:

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

Rules:

- retryable failure ends only the attempt;
- abort ends only the operation/round;
- module unavailability does not stop independent modules;
- only fatal failure automatically stops the process;
- emergency stop releases inputs and exits immediately;
- `NOT_FOUND`, `TIMEOUT`, and `FAILED` are not inherently fatal.

Retries repeat only the failed stage.

After a confirmed one-shot action, polling must not repeat the action. Examples: trainer click, message send, subprocess start, and session finalization.

## 15. Workers, tasks, timers, and subprocesses

Every worker must define:

- owner;
- name;
- start condition;
- stop condition;
- timeout;
- cancellation;
- cleanup;
- result;
- retry;
- failure impact.

`daemon=True` is not lifecycle management.

A monitor cancelled during a critical transaction must resume in `finally` unless shutdown is permanent.

Subprocesses require exit code, timeout, bounded terminate/kill, secret-free logs, and input cleanup.

## 16. Protocols and localization

API/WebSocket surfaces should prefer stable codes:

```text
INVALID_TOKEN
GAME_NOT_FOUND
FOREGROUND_FAILED
IC_INPUT_NOT_FOUND
STATS_WINDOW_CHANGED
```

The UI maps codes to PT-BR or EN-US.

Do not use localized prose as a protocol contract. Controllers/services must not create visible prose when a localization layer exists.

PT-BR and EN-US are first-class official languages. New keys must exist in both languages before completion.

Do not translate IDs, JSON fields, filenames, or technical codes.

## 17. Security and privacy

Never version or log:

- access tokens;
- query-string tokens;
- secure-storage contents;
- private URLs containing secrets;
- personal `config.json`;
- history database;
- personal RAW/Vault;
- personal visual datasets;
- sensitive logs;
- raw tracebacks in UI.

Prepared cloudflared and external dependencies must have verified version and SHA-256.

## 18. Persistence and upgrades

Normal upgrades preserve, when applicable:

- configuration;
- token;
- history;
- OOC/IC calibration;
- parser state;
- LeafOS settings;
- Android profiles;
- favorites;
- GAME bank and mappings.

Destructive migration requires explicit authorization and rollback.

## 19. Mandatory change workflow

1. refresh `main`;
2. read the Bible and component documentation;
3. create a branch;
4. reproduce/define expected behavior;
5. locate duplicate implementations;
6. change the canonical source;
7. update consumers/tests/docs;
8. run available tests;
9. review the diff;
10. open a PR with validation limitations;
11. validate physically when Windows/BYOND requires it;
12. merge only after approval.

## 20. Minimum tests

Python:

```powershell
python -m unittest discover -s tests -v
python -m compileall .
```

Flutter:

```text
flutter analyze
flutter test
```

Kage Pilot:

```powershell
python -m compileall -q pc_agent/kage_pilot
python -m py_compile kage_pilot.py kage_pilot_loop.py
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
python kage_pilot.py dojo --show-config
```

Add proportional tests for success, absence, timeout, retry, cancellation, shutdown, corrupted state, replaced window, wrong PID, foreground loss, and cleanup.

Never claim a test passed unless it actually ran.

## 21. Release

CI must fail when version, backend, Android, installer, documentation, or artifacts drift.

Workflows read `RELEASE_VERSION`; they do not hardcode the current version in paths.

Changes to `AGENTS*`, protocols, persisted state, entry points, workflows, installer, or localization trigger the relevant regression jobs.

## 22. Definition of done

A task is complete when:

- the active source was identified;
- the packaged entry point was considered;
- scope was preserved;
- duplicates were removed or justified;
- failure class and cleanup are clear;
- persisted state has a corruption policy;
- tests passed or limitations were recorded;
- PT-BR/EN-US were verified;
- documentation is current;
- rollback exists;
- required real-world validation is recorded;
- no correct version exists only in ZIP/Desktop;
- GitHub contains the traceable result.

# Final commandment

> **KageLink must evolve without losing what already works. GitHub is official memory; `Says:` is an exact contract; chat, GAME, STATS, LeafOS, and Kage Pilot remain coherent, isolated, safe, and traceable.**
