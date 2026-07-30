# KageLink — Development Bible

[Português](AGENTS.md) · [English README](README.md) · [Kage Pilot](KAGE_PILOT.en.md) · [Runtime](AGENTS_RUNTIME.en.md) · [Dojo](AGENTS_DOJO.en.md) · [Interpreter](AGENTS_INTERPRETER.en.md)

This file is the operational source of truth for every person or AI agent changing KageLink.

## 1. Official source

Official repository: `leafoss/KageLink`.

**GitHub is the only official source of code.** ZIP files, Desktop folders, installed builds, isolated APK/EXE files, pasted files, and uncommitted copies are auxiliary material only.

Required flow:

```text
main → branch → minimal change → tests → diff review → PR → real validation → merge
```

## 2. Official version

Current version:

```text
KageLink 3.5.0
```

`RELEASE_VERSION` is the editable version source. CI must keep the PC Agent, Flutter, Inno Setup, builders, artifact names, `/api/health`, READMEs, and releases aligned.

## 3. Core philosophy

**Do not break working behavior.**

Changes must be minimal, localized, traceable, testable, and compatible with unrelated working behavior.

Do not use a limited task to perform aesthetic refactors, incidental folder reorganizations, dependency swaps, unrelated UI/protocol changes, destructive resets, whole-module replacement, or unrequested scope expansion.

When Rafael says “change only X”, treat it as a hard constraint.

## 4. Official 3.5.0 architecture

Products:

1. Android App — Flutter.
2. Desktop/PC Agent — Windows/Python.
3. Windows Installer.
4. Installed Kage Pilot Dojo runtime.
5. Optional LeafOS integration.

Distributed runtime:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

The packaged route layers `unified_*` components over legacy code. Before editing, identify the packaged entrypoint, actual class, runtime replacement/monkeypatch, PyInstaller spec, and test following the same route.

A fix is not complete when it only changes a layer unused by the official executable.

## 5. One canonical source per responsibility

Domain decisions must have one canonical implementation.

Examples:

- OOC/IC: `ChatChannelParser`.
- canonical memory: `memory.json` after human review.
- Kage Pilot public surface: `kage_pilot.py`.
- Pilot documentation: `KAGE_PILOT.md` and `KAGE_PILOT.en.md`.
- release version: `RELEASE_VERSION`.

Active files are named by responsibility, not version. Do not create new `v03x`, `final2`, `new`, or `hotfix` filenames. Git stores history.

Versioned modules still composing the physically validated engine may remain temporarily as compatibility layers, but they must not become new public surfaces. Removal requires semantic extraction, a green suite, and renewed real-game validation.

## 6. OOC / IC protected contract

`(* ... *)` blocks are IC/RP, including fragmented blocks.

The dialogue marker is literal and case-sensitive:

```text
Says:
```

`**Anbu** Says: test` is IC. `says:`, `SAYS:`, and `sAyS:` do not activate this rule.

Speaker names may contain spaces, commas, apostrophes, clan names, and Markdown. Do not require a rigid name regex for channel classification.

Android uses `/api/send/ooc` and `/api/send/ic`. The Agent selects only the requested channel control and never silently falls back to the other channel.

## 7. History, RAW, and memory

Preserve IDs, timestamps, direction, channel, parser state, cursors, and resynchronization behavior.

RAW is append-only and receives the already classified channel.

Pipeline:

```text
immutable RAW → Processor → closed session → Interpreter → pending_review Bundle → human Reviewer → Canonical Memory
```

The Interpreter creates candidates, never automatic canonical truth. Evidence must resolve back to `source_message_ids`.

`memory.json` is computable truth; `MEMORY.md` is a regenerable projection.

## 8. Persisted-state integrity

Each persisted file declares one policy:

- **fail closed:** RAW, sessions, Reviewer, Canonical Memory, identity, and evidence cursors;
- **quarantine and rebuild:** only proven reconstructible cache/checkpoint state;
- **backup and defaults:** recoverable configuration with an explicit warning.

Existing invalid cursor, session, or identity state must never be silently treated as empty.

New message IDs must be greater than every ID already present in SQLite, RAW, Processor state, or Vault.

## 9. GAME, STATS, and Windows automation

GAME, STATS, Dojo, or LeafOS failures must not stop independent chat or runtime modules.

Before a click, key-down, text write, or fallback capture:

1. locate the target again;
2. validate HWND;
3. validate title/class;
4. validate PID/process;
5. validate root/child relationship;
6. validate visibility and reject minimized targets;
7. confirm foreground when required;
8. revalidate immediately before input;
9. verify coordinates are inside the client;
10. guarantee mouse-up/key-up and cleanup.

Never trust stale HWNDs or coordinates blindly.

GAME and STATS must not become generic desktop control surfaces. Preserve keyboard whitelists, protocol limits, and module isolation.

## 10. Kage Pilot / Dojo

`KAGE_PILOT.en.md` and `AGENTS_DOJO.en.md` apply.

Permanent contracts:

- exactly one Trainer click per round;
- dialog retries never repeat Trainer search, movement, or click;
- one initial wait/check plus up to three additional checks;
- final dialog failure ends only the round when safe;
- F12 releases inputs and stops the loop;
- manual GAME input is blocked during autonomous training;
- 32×32 and 64×64 templates belong to the user and live under `%LOCALAPPDATA%\KageLink\data\kage_pilot\templates`;
- normal updates preserve templates;
- missing valid templates fail closed;
- recovery floors are HP ≥ 90% and Chakra ≥ 50%.

## 11. Failures, retries, and shutdown

Normative outcomes:

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

`NOT_FOUND`, `TIMEOUT`, and `FAILED` are not inherently fatal.

Retries repeat only the failed stage. A confirmed one-shot action must not be repeated while polling for its result.

Every thread, task, timer, watcher, and subprocess defines owner, start, stop, timeout, cancellation, cleanup, result, retry policy, and failure impact. `daemon=True` is not lifecycle management.

## 12. Protocols, localization, and security

PT-BR and EN-US are first-class languages.

API/WebSocket surfaces should return stable codes such as `INVALID_TOKEN`, `GAME_NOT_FOUND`, and `DOJO_TRAINER_TEMPLATE_REQUIRED`. UI layers translate codes; services/controllers should not create hardcoded visible prose.

Never log access tokens, secret query strings, secure-storage values, full private URLs, personal RAW, or complete sensitive payloads.

KageLink never executes arbitrary system commands, programs, or scripts received from clients.

## 13. Release and Installer

Fix Agent source, not only the installer.

Every release validates:

- full Python suite;
- `compileall`;
- Flutter localization/analyze/test;
- build and smoke of `KageLink.exe`;
- build and `--help` of `KagePilotDojo.exe` and `KagePilotRound.exe`;
- Windows Setup;
- APK;
- version parity;
- asset/template contract;
- user-data preservation during normal upgrade.

## 14. Required workflow

1. update `main`;
2. create a branch;
3. reproduce and understand the state;
4. locate all related implementations;
5. make the minimal change;
6. run risk-proportional tests;
7. review the diff;
8. remove unnecessary lines;
9. create a clear commit;
10. open a draft PR;
11. perform real validation when applicable;
12. merge only after approval.

Never claim a test passed when it was not executed.

## 15. Definition of done

A change is ready when the active source and packaged entrypoint were identified, failure/retry/cleanup are defined, persisted state has a corruption policy, PT-BR and EN-US remain equivalent, relevant tests passed or limitations are recorded, versions and artifacts align, required physical validation is recorded, no known unrelated changes remain, and no correct version exists only in a ZIP, Desktop folder, or local build.
