# KageLink — Runtime, Persistence, and Organization Bible

[Português](AGENTS_RUNTIME.md) · [Main Bible](AGENTS.en.md) · [Kage Pilot](KAGE_PILOT.en.md)

This document complements `AGENTS.en.md` and governs the actual executable composition, workers, persistence, Windows automation, failures, retries, versioning, and repository organization.

## 1. Official executable composition

The packaged runtime follows:

```text
KageLink.spec
→ unified_entry.py
→ unified_launcher.py
→ kagelink_launcher.py
→ unified_app.py
→ app.py
```

This route includes inheritance, module replacement, and runtime Interpreter selection. Before changing the PC Agent, identify:

1. the packaged entry point;
2. the class actually instantiated;
3. the backend actually imported;
4. applicable monkeypatch/replacement behavior;
5. a test that follows the same route;
6. compatibility-only legacy modules.

A fix is not complete when it only changes a layer unused by the official executable.

## 2. Version source

`RELEASE_VERSION` is the only human-edited release version source.

CI must verify consistency across:

- `RELEASE_VERSION`;
- `pubspec.yaml`;
- Inno Setup;
- backend and `/api/health`;
- Android labels;
- artifact names;
- workflows;
- READMEs and release documentation.

Avoid hardcoded version numbers in user-visible text.

## 3. Failure classes

Every operational outcome must belong to one class:

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

- retryable failures end only the attempt;
- aborts end only the operation or round;
- module unavailability does not stop independent modules;
- only fatal failures stop the process automatically;
- emergency stop releases inputs and exits immediately;
- `NOT_FOUND`, `TIMEOUT`, and `FAILED` are not inherently fatal.

## 4. Retry and one-shot actions

Retries repeat only the failed stage.

Once a one-shot action succeeds, polling for its response must not repeat that action.

Every retry policy must declare:

- initial wait;
- retry count and total checks;
- interval;
- success condition;
- abort condition;
- effect on the parent loop;
- interruption behavior.

## 5. Mandatory window/input gate

Before any click, key-down, text write, or fallback capture:

1. locate the target again;
2. validate HWND;
3. validate title and class;
4. validate PID/process;
5. validate root/child relationship;
6. validate visibility;
7. reject minimized targets;
8. confirm foreground when required;
9. revalidate immediately before input;
10. verify coordinates are inside the client;
11. execute;
12. guarantee mouse-up/key-up and cleanup.

Never trust stale frame HWNDs or coordinates blindly.

## 6. Worker ownership

Every thread, task, timer, watcher, and subprocess must define:

- owner;
- name;
- start condition;
- stop condition;
- timeout;
- cancellation;
- cleanup;
- result;
- retry policy;
- failure impact.

`daemon=True` does not replace explicit lifecycle management.

A monitor temporarily cancelled for a transaction must resume in `finally` unless shutdown is permanent.

## 7. State integrity

Every persisted file must declare one policy.

### Fail closed

For RAW, sessions, Reviewer state, Canonical Memory, evidence cursors, and identity state.

### Quarantine and rebuild

Only for state proven to be reconstructible from intact sources.

### Backup and defaults

For recoverable configuration, with an explicit warning.

Existing but invalid cursor, session, or identity state must never be silently treated as empty.

## 8. Evidence IDs

Message IDs are identity.

New IDs must be greater than every ID already present in:

- SQLite;
- RAW;
- Processor;
- Vault.

Migration or reinstall must not restart IDs below `last_processed_id`.

## 9. Protocols and localization

API and WebSocket surfaces return stable codes such as:

```text
INVALID_TOKEN
GAME_NOT_FOUND
FOREGROUND_FAILED
IC_INPUT_NOT_FOUND
STATS_WINDOW_CHANGED
```

The UI maps codes to PT-BR or EN-US.

Do not:

- use localized prose as a protocol contract;
- create visible prose in controllers/services when localization exists;
- display tracebacks or internal details directly to users;
- translate IDs, JSON fields, or technical codes.

## 10. Log security

Never log:

- access tokens;
- query-string tokens;
- secure-storage contents;
- full private URLs containing secrets;
- unnecessary personal RAW;
- unrelated window titles;
- complete sensitive payloads.

Prefer structured fields:

```text
component
operation
error_code
recoverability
attempt
session_id/round_id
elapsed
```

## 11. Repository organization

The active tree contains only:

- canonical entry points;
- modules imported by the runtime;
- permanent tests;
- example/canonical configuration;
- current documentation.

Do not keep in the active tree:

- replaced `v03a`, `v03b`, or `v03c` copies;
- disposable probes;
- manual scripts already absorbed by automated tests;
- milestone reports used as current manuals;
- duplicated PT/EN files without a clear canonical relationship.

Git history is the archive for old versions. When consolidating an implementation:

1. create a non-versioned canonical name;
2. update imports, subprocesses, workflows, tests, and documentation;
3. validate the suite;
4. remove replaced snapshots;
5. record migration and rollback in the PR.

Do not merge distinct responsibilities into a monolith merely to reduce file count.

## 12. Release contract

CI must fail on version drift across documentation, backend, Android, installer, or artifacts.

Workflows must read `RELEASE_VERSION` instead of hardcoding the current version.

Changes to `AGENTS*.md`, protocols, persisted state, entry points, workflows, installer, or localization must trigger relevant jobs.

## 13. Additional minimum tests

Preserve or add tests for:

- version synchronization;
- packaged runtime routing;
- corruption of each persisted state;
- task/thread/subprocess cleanup;
- window replacement between detection and click;
- wrong PID;
- foreground loss;
- retry without repeating a one-shot action;
- operation failure without stopping the parent loop;
- localized controller/service errors;
- Flutter reconnect and HTTP reconciliation;
- GAME/STATS control release on dispose/disconnect.

## 14. Definition of done

A runtime or organization change is complete only when:

- the active source was identified;
- the packaged entry point was considered;
- the failure class was defined;
- cleanup was demonstrated;
- affected persisted state has a corruption policy;
- protocols remain stable;
- PT-BR and EN-US were verified;
- tests cover success, absence, timeout, retry, cancellation, and shutdown proportionally to risk;
- version and artifacts are synchronized;
- required real validation is recorded;
- no correct implementation exists only in a ZIP, Desktop copy, or local build.
