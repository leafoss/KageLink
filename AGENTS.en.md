# KageLink — Development Bible

[Português](AGENTS.md) · [README](README.md) · [Kage Pilot](KAGE_PILOT.en.md) · [Dojo](AGENTS_DOJO.en.md) · [Interpreter](AGENTS_INTERPRETER.en.md)

This file is the **operational source of truth for every person or agent changing KageLink**. Specialized chapters extend this Bible; when rules appear to conflict, apply the more conservative rule for safety, data integrity, and traceability.

## 1. Official source

Canonical repository:

```text
https://github.com/leafoss/KageLink
```

**GitHub is the only official source of code.**

Do not treat these as primary sources:

- old ZIP files;
- Desktop copies;
- installed builds;
- isolated APK or EXE files;
- files pasted into conversations;
- uncommitted local folders.

Mandatory flow:

```text
main
→ work branch
→ smallest sufficient change
→ tests
→ diff review
→ Pull Request
→ real-world validation when required
→ explicit approval
→ merge
```

## 2. Official version

The only human-edited version source is:

```text
RELEASE_VERSION
```

Current version:

```text
KageLink 3.5.0
```

CI and release must keep these aligned:

- `RELEASE_VERSION`;
- `pubspec.yaml`;
- Inno Setup;
- PC Agent and `/api/health`;
- manual build scripts;
- UI labels;
- artifact names;
- workflows;
- READMEs.

Do not maintain manually edited version numbers in multiple surfaces when the canonical value can be read or generated.

## 3. Core philosophy

**Do not break working behavior.**

Every change must be:

- traceable;
- reversible;
- testable;
- limited to scope;
- compatible with unrelated modules.

Do not perform aesthetic refactors, dependency swaps, protocol changes, destructive cleanup, or incidental reorganization without an explicit request.

When Rafael authorizes reorganization, it must include:

1. a file inventory;
2. identification of the active source;
3. import, spec, workflow, and documentation updates;
4. regression tests;
5. Git rollback;
6. real validation when Windows/BYOND/input is involved.

## 4. Products and responsibilities

### Android App

Owns UI, profiles, secure token storage, OOC, IC/RP, GAME, STATUS, remote Dojo control, HTTP/WebSocket, reconnect behavior, language, and local preferences.

Android never executes computer vision, keyboard input, combat logic, or Dojo autonomy.

### PC Agent

Owns game discovery, chat and image capture, message classification, history, OOC/IC sending, authentication, API/WebSockets, GAME/STATUS control, LeafOS integration, and Kage Pilot execution on Windows.

### Installer

Packages exactly the current source, includes verified dependencies, preserves user data during normal upgrades, and installs:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

Never fix Agent behavior only in the Installer. Fix the source and prove that the build packages the corrected source.

### LeafOS

Optional and disabled by default. LeafOS failures must not stop chat, GAME, STATUS, Desktop, tunnel, or Dojo.

## 5. Packaged runtime

The official Desktop is composed through:

```text
KageLink.spec
→ unified_entry.py
→ unified_launcher.py
→ kagelink_launcher.py
→ unified_app.py / active integration layer
→ app.py
```

The architecture uses inheritance, module replacement, and compatibility layers. Before changing behavior, identify:

1. the packaged entry point;
2. the class actually instantiated;
3. the backend actually imported;
4. applicable monkeypatch or facade behavior;
5. a test that follows the same route;
6. compatibility-only files.

Editing a layer unused by the executable is not a completed fix.

## 6. One canonical source per responsibility

General rule:

```text
one responsibility
→ one canonical module
→ consumers reuse that module
```

Historical versions belong in Git, not the active tree as:

```text
final2.py
v03l.py
hotfix_new.py
copy.py
```

A temporary compatibility layer must be small, identified, tested, and have a removal condition.

### Kage Pilot

Human-facing public surface:

```text
KageLink Installer/pc_agent/kage_pilot.py
```

Canonical command:

```powershell
python kage_pilot.py dojo
```

The Installer uses versionless internal entry points inside `pc_agent.kage_pilot`. The physically validated chain may retain historical internal names until semantic extraction is validated; those names must not return as public commands.

Active documentation:

```text
KAGE_PILOT.md
KAGE_PILOT.en.md
AGENTS_DOJO.md
AGENTS_DOJO.en.md
```

## 7. OOC / IC contract — PROTECTED RULE

### IC blocks

Every block starting with `(*` and ending at the next `*)` is IC/RP. Fragmented blocks remain pending until closure.

### IC dialogue

The valid marker is literal and case-sensitive:

```text
Says:
```

IC examples:

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

A speaker name may contain spaces, commas, apostrophes, clan names, and Markdown. Channel classification must not depend on a rigid name regex.

## 8. OOC / IC sending

Dedicated endpoints:

```text
/api/send/ooc
/api/send/ic
```

`/api/send` exists only for compatibility.

The Agent must:

1. receive an explicit channel;
2. revalidate the game window;
3. re-locate controls;
4. select only the requested field;
5. reject when the field is absent;
6. never silently use the other channel.

One HWND must not represent OOC and IC at the same time.

## 9. History, IDs, and evidence

Preserve:

- IDs;
- timestamps;
- direction;
- channel;
- parser state;
- resynchronization;
- RAW/Processor cursors;
- character history;
- evidence IDs.

IDs are identity, not disposable ordering.

New IDs must be greater than every ID already present in SQLite, RAW, Processor, or Vault. Reinstallation must not restart IDs below `last_processed_id`.

Do not delete databases or configuration as the default fix.

## 10. LeafOS and memory

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
- `channel` comes from the canonical parser;
- Processor does not reprocess IDs;
- Interpreter creates candidates, not automatic truth;
- Reviewer is the human gate;
- evidence traces back to RAW;
- `memory.json` is the computable source;
- `MEMORY.md` is a regenerable projection;
- invalid canonical JSON blocks destructive reads/writes.

For Interpreter/Reviewer work, also read `AGENTS_INTERPRETER.en.md`.

## 11. Persisted-state policy

Every persisted file must declare one policy:

### Fail closed

RAW, sessions, Reviewer, Canonical Memory, identity, and evidence cursors. Existing invalid state must never silently become empty.

### Quarantine and rebuild

Only for cache or checkpoint proven reconstructible from intact sources.

### Backup and defaults

Recoverable configuration may be backed up before defaults are applied, with an identifiable warning.

## 12. Windows window/input gate

Before a click, key-down, text write, or fallback capture:

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

Never blindly trust an old-frame HWND or coordinate.

## 13. GAME

GAME remains isolated from chat, STATUS, and LeafOS.

- prefer window-specific capture;
- allow region fallback only after target/foreground confirmation;
- use a key whitelist;
- preserve heartbeat and dead-man behavior;
- disconnect, error, screen change, and dispose release keys;
- GAME cannot execute programs, scripts, URLs, or system commands.

While Kage Pilot is active, Windows blocks manual GAME control rather than relying only on disabled UI controls.

## 14. STATUS

Expected window:

```text
Title: Status | Inventory
Class: #32770
```

Before a frame or click, validate the same game PID, expected HWND, class, title, visibility, non-minimized state, and client-bound coordinates.

STATUS is not generic desktop control.

## 15. Kage Pilot and Dojo

Read `AGENTS_DOJO.en.md` before changing:

- templates;
- Trainer vision;
- round loop;
- combat;
- KO;
- return/recovery;
- Dojo API;
- Desktop/Android UI;
- Installer/helpers;
- GAME interlock.

Global contracts:

- one Trainer click per round;
- retries repeat only the failed stage;
- F12 remains emergency stop;
- every exit releases inputs;
- minimum HP 90%; minimum Chakra 50%;
- Android is remote control, not decision authority;
- Settings remains the final Desktop sidebar item.

## 16. Failures, retries, and continuity

Recommended taxonomy:

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

Rules:

- a retryable failure ends only the attempt;
- an abort ends only the operation or round;
- module unavailability preserves independent modules;
- only a proven fatal failure ends the process;
- emergency stop releases inputs and exits immediately;
- `NOT_FOUND`, `TIMEOUT`, and `FAILED` are not inherently fatal.

A confirmed one-shot action must not be repeated while polling for its response.

Every retry policy must state the initial wait, retry count, total checks, interval, success condition, abort condition, effect on the parent loop, and interruption behavior.

## 17. Threads, tasks, timers, and subprocesses

Every worker must define:

- owner;
- name;
- start condition;
- stop condition;
- timeout;
- cancellation signal;
- cleanup;
- observable result;
- retry policy;
- failure impact.

`daemon=True` is not lifecycle management.

A monitor cancelled for a critical transaction must be resumed in `finally` unless shutdown is permanent.

Subprocesses must record a secret-free command, exit code, timeout, terminate/kill policy, input cleanup, and orphan prevention.

## 18. Localization

PT-BR and EN-US are first-class languages.

Every user-facing surface must support both:

- Desktop;
- Android;
- errors and states;
- tooltips;
- onboarding;
- product documentation.

API and WebSocket surfaces should prefer stable technical codes. Presentation layers translate those codes. Controllers/services must not create visible hardcoded prose when localization exists.

IDs, JSON fields, routes, and technical codes are not translated.

## 19. Security and privacy

Never version or log:

- access tokens;
- query-string tokens;
- private/temporary URLs;
- secure-storage contents;
- personal RAW;
- history databases;
- personal configuration;
- user templates, calibration, or frames;
- sensitive logs;
- private Vault contents.

Logs should prefer component, operation, code, recoverability, attempt, round/session ID, and elapsed time.

Packaged external dependencies must have a verified version and hash.

## 20. Release and Installer

The official Release is rebuilt from `main`; temporary PR artifacts do not replace distribution.

Stable assets:

```text
KageLink-Windows-Setup.exe
KageLink-Android.apk
SHA256SUMS.txt
```

Minimum gate:

1. full Python suite;
2. compileall;
3. Flutter tests and localization;
4. `KageLink.exe` build;
5. `KagePilotDojo.exe` build;
6. `KagePilotRound.exe` build;
7. helper smoke tests;
8. Desktop smoke test;
9. Setup containing all three executables;
10. release APK;
11. risk-proportional real test;
12. explicit approval before merge/publication.

## 21. Minimum tests by area

### Parser/chat

- fragmented blocks;
- literal `Says:`;
- complex names;
- OOC/IC without cross-channel fallback;
- replay and resync.

### LeafOS

- cursors and IDs;
- RAW append-only;
- state corruption;
- session close/resume;
- evidence;
- Reviewer/Canonical fail closed.

### GAME/STATUS

- absent/minimized/replaced window;
- wrong PID;
- foreground loss;
- disconnect;
- key release;
- frame/coordinate identity.

### Dojo

- missing runtime/templates;
- single click;
- dialog checks 1–4;
- aborted round without stopping the loop;
- F12 during waits;
- subprocess nonzero/timeout;
- repeated KO;
- return and recovery;
- Desktop/Android/interlock;
- helper packaging.

## 22. Change process

1. update `main`;
2. create a branch;
3. read this Bible and applicable chapters;
4. reproduce/map behavior;
5. locate every implementation and consumer;
6. make the smallest sufficient change;
7. update PT-BR/EN-US;
8. run tests;
9. review the diff;
10. open a draft PR;
11. validate in the real environment when needed;
12. merge only after an explicit decision.

Mandatory diff question:

> Is any changed line unnecessary for this task?

If yes, remove it.

## 23. Validation honesty

Never claim a test passed when it was not executed.

Distinguish:

- static inspection;
- automated test;
- build;
- smoke test;
- physical Windows/BYOND validation;
- user confirmation.

When the environment cannot execute the code, record the limitation and use PR CI as a gate before merge.

## 24. Definition of done

A task is complete only when:

- the active source was identified;
- the change exists in the correct destination;
- scope was checked;
- cleanup was demonstrated;
- persisted state is protected;
- protocol contracts remain stable;
- PT-BR and EN-US are covered;
- proportional tests were run;
- build/Installer impact was considered;
- documentation is current;
- no official version exists only in a ZIP/Desktop folder;
- the next action and pending validation are explicit.
