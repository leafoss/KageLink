# KageLink — Development Bible

[Português (Brasil)](AGENTS.md) · [English README](README.md) · [README em Português](README.pt-BR.md)

This document is the **operational source of truth for any person or AI agent modifying KageLink**.

Its purpose is to prevent regressions, diverging versions, unnecessary refactors, documentation that promises nonexistent features, and the old ZIP-based workflow.

Before modifying code, read this file and the files directly related to the task.

---

## 1. Official project source

Official repository:

```text
https://github.com/leafoss/KageLink
```

### Absolute rule

**GitHub is the only official source of KageLink code.**

Do not treat the following as the primary source:

- old ZIP archives;
- Desktop copies;
- uncommitted local folders;
- already-installed builds;
- isolated files shared in conversations;
- an EXE/APK that cannot be traced to a commit.

If a feature exists only locally, it is not an official `main` feature until it is brought into GitHub and validated.

### Official workflow

```text
main
  ↓
working branch
  ↓
minimal change
  ↓
tests
  ↓
diff review
  ↓
Pull Request
  ↓
validation
  ↓
merge
```

---

## 2. Documentation languages

The Development Bible has two versions:

- `AGENTS.md` — Brazilian Portuguese;
- `AGENTS.en.md` — English.

Both files must represent the **same technical rules**.

When a permanent rule changes, update both in the same PR whenever possible.

The READMEs follow the same model:

- `README.pt-BR.md`;
- `README.md` in English.

---

## 3. Current official state

The version currently identified on `main` is:

```text
KageLink 3.3.0 — GAME V1
```

Official components:

1. **KageLink Android App** — Flutter/Android;
2. **KageLink PC Agent** — Windows/Python;
3. **KageLink Windows Installer** — packages the PC Agent.

The Android APK and Windows installer are separate artifacts with separate build pipelines.

### Important

The Windows installer **does not build the APK**.

The APK is built by:

```text
KageLink Installer\COMPILAR_APK.bat
```

The PC Agent installer is built by:

```text
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

---

## 4. Core philosophy

KageLink is a working project used in a real environment.

### Primary commandment

> **Do not break working behavior.**

Every change must be:

- minimal;
- localized;
- traceable;
- justified;
- testable;
- compatible with existing behavior unless the task explicitly requires a behavior change.

### Do not

- refactor for aesthetics during a bug fix;
- rename files/classes/routes without need;
- reorganize folders during a bug fix;
- replace dependencies without a functional reason;
- modify UI incidentally;
- change protocol during a local fix;
- change control mappings without a request;
- delete history/configuration to “solve” a bug;
- replace an entire module when a small change is sufficient;
- use a tightly scoped task as an excuse to “improve” unrelated areas.

A parser fix does not authorize GAME changes.

A GAME fix does not authorize chat changes.

A documentation change does not authorize production behavior changes, except when the documentation review reveals a small defect directly tied to the documented flow and that correction is explicit and reviewable.

---

## 5. Official architecture

Primary layout:

```text
KageLink/
├── AGENTS.md
├── AGENTS.en.md
├── README.md
├── README.pt-BR.md
├── LICENSE
└── KageLink Installer/
    ├── COMPILAR_APK.bat
    ├── DIAGNOSTICAR_KAGELINK.bat
    ├── android_overlay/
    ├── assets/
    ├── installer/
    │   ├── CRIAR_INSTALADOR.bat
    │   ├── KageLink.spec
    │   └── KageLink_PC_Agent.iss
    ├── lib/
    ├── pc_agent/
    ├── test/
    ├── analysis_options.yaml
    ├── l10n.yaml
    └── pubspec.yaml
```

Before editing any file, determine which component actually controls the observed behavior.

---

## 6. Separation of responsibilities

### Android App

Primarily responsible for:

- connection/profile UI;
- OOC;
- IC/RP;
- GAME;
- history presentation;
- HTTP/WebSocket connectivity;
- reconnect behavior;
- secure profile-token storage;
- navigation;
- language;
- user-requested input calibration;
- GAME controls sent through the allowed protocol.

### PC Agent

Primarily responsible for:

- locating `Shinobi Story Online`;
- reading chat;
- classifying OOC/IC;
- maintaining history and parser state;
- locating OOC/IC inputs;
- sending text to the game;
- client authentication;
- API/WebSockets;
- local server;
- Cloudflare Tunnel;
- GAME capture;
- GAME control;
- game-window focus;
- stuck-key protection.

### Installer

Responsible for:

- packaging the current PC Agent source;
- including runtime dependencies;
- including validated `cloudflared`;
- installing `KageLink.exe`;
- preserving data during normal updates;
- offering explicit data removal during uninstall.

**Never fix an Agent bug only in the installer. Fix the Agent source, then make sure the installer packages that source.**

---

## 7. One source for domain decisions

When the same decision appears in multiple project areas, there should be one canonical implementation whenever possible.

Critical example:

```text
OOC/IC classification
```

Correct conceptual flow:

```text
captured text
    ↓
ChatChannelParser
    ↓
classified message
    ├── history
    ├── API/WebSocket
    └── application
```

Do not create independent rules for UI, history, and backend when all can consume the already-classified `channel`.

Any future RAW integration must also consume that canonical classification rather than introducing a second diverging parser.

---

## 8. Official OOC / IC classification contract

This behavior is protected.

### 8.1 IC roleplay blocks

Every block beginning with:

```text
(*
```

and ending at the next:

```text
*)
```

is IC/RP.

Example:

```text
(*Uchiha, Leafos nods.*)
```

Blocks may arrive fragmented across reads. The parser must keep the block pending until the closing delimiter arrives.

### 8.2 IC speech through `Says:`

The official current rule is **literal and case-sensitive**.

The valid marker is exactly:

```text
Says:
```

IC examples:

```text
**Anbu** Says: ???
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

Examples that do not activate this rule and remain in the OOC flow when no other IC rule applies:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: test
```

### Hard rule

**Do not make `Says:` case-insensitive without a new explicit project decision.**

This rule was fixed in the canonical parser and has regression tests.

### Speaker names

Do not assume the speaker name is one word. Text may contain:

- commas;
- spaces;
- apostrophes;
- clan + name;
- Markdown/asterisks such as `**Anbu**`;
- other formats emitted by the game.

The current implementation detects the marker in the line without depending on a rigid speaker-name format.

### OOC

Everything that does not satisfy a valid IC rule remains OOC.

Do not alter OOC behavior during an IC-only fix.

---

## 9. OOC / IC send contract

OOC and IC are separate destinations.

The Agent must:

1. locate the game window;
2. confirm focus;
3. locate `Edit` controls again;
4. select the control matching the requested channel;
5. block the send if the control is not found;
6. never silently fall back to the other channel.

The same HWND cannot safely represent OOC and IC at the same time.

When automatic detection is insufficient, the app provides separate calibration.

---

## 10. History and persistence

Chat history belongs to the PC Agent and uses SQLite.

User data that should be preserved during normal updates when applicable:

- `config.json`;
- access key;
- history database;
- OOC/IC preferences;
- persistent parser state;
- logs;
- other compatible installation settings.

Never solve a bug by deleting the database, configuration, or history as the default behavior.

Destructive migration requires explicit approval and a backup/migration strategy.

---

## 11. RAW / Obsidian — status and contract

### Status of `main` 3.3.0

The Bible records the desired contract for RAW/Obsidian integration, but the current official `main` source **does not expose RAW configuration in `AppConfig`**.

Therefore:

- do not advertise RAW/Obsidian as a standard 3.3.0 release feature;
- do not assume RAW generated by a local build exists in GitHub;
- if the implementation exists only outside the repository, bring it into a branch first.

### Contract for future official RAW integration

The integration must:

- use the same message already classified by the canonical parser;
- not reclassify OOC/IC inside the writer;
- work while Obsidian is closed;
- keep the destination path configurable;
- create directories when appropriate;
- use UTF-8;
- preserve raw text;
- prefer daily organization when that is the approved format;
- append without unnecessarily rewriting old history;
- preserve enough metadata for timestamp/id/channel;
- handle replay/duplication;
- never commit personal RAW data.

Reference format previously used during development:

```html
<!-- kagelink-raw-begin {"id":7538,"timestamp":"...","channel":"ic","speaker":null} -->
original message
<!-- kagelink-raw-end -->
```

This format becomes official only when the corresponding implementation is also in the repository.

---

## 12. GAME contract

GAME is deliberately isolated from chat.

A GAME failure must not take down:

- OOC;
- IC/RP;
- history;
- authentication;
- parser;
- chat sending.

### Target window

```text
Shinobi Story Online
```

Do not turn KageLink into a generic desktop remote-control tool.

### GAME V1 stream

Current contract:

- JPEG;
- `960 × 540`;
- approximately `8–12 FPS` target;
- no audio;
- Full mode;
- central Zoom mode;
- separate connection from the chat WebSocket;
- no intentionally growing frame queue.

### Orientation

- OOC/IC: portrait;
- GAME: landscape;
- leaving GAME: restore portrait.

### Focus

When GAME activates, the client requests a `focus_click`.

The Agent:

1. validates the target window;
2. rejects a minimized game;
3. brings the game forward;
4. clicks the center of the captured area.

---

## 13. Protected GAME controls

Current mapping:

```text
Joystick -> arrow keys
A -> E
B -> Space
C -> G
D -> V
```

Current whitelist:

```text
up, down, left, right, e, space, g, v
```

Do not silently add:

- Alt+F4;
- Windows key;
- Ctrl+Esc;
- arbitrary commands;
- program execution;
- generic macros;
- broad desktop control.

### Stuck keys

The project must continue releasing key state when:

- leaving GAME;
- backgrounding the app;
- losing the connection;
- losing focus unsafely;
- losing the game window;
- hitting heartbeat timeout;
- closing the Agent/session.

---

## 14. Connectivity and security

### Local network

The Agent publishes its server on the configured host, currently `0.0.0.0`, with default port `8765`.

The UI calculates and displays the current local address.

If the port is occupied, the Agent may choose another port and persist it.

### Cloudflare

By default, external connectivity uses Cloudflare Quick Tunnel.

The Agent:

- prepares/validates `cloudflared`;
- checks SHA-256;
- checks the executable header;
- validates the expected version;
- starts a tunnel to the local server;
- extracts the `trycloudflare.com` URL;
- writes connection information.

### Token

The access key:

- is generated automatically;
- must have appropriate entropy;
- is required for authentication;
- must not appear in public logs or commits;
- can be regenerated from Agent Settings.

Regenerating the key invalidates credentials already stored in Android profiles.

### Private files

Never commit:

- user `config.json`;
- a real `KAGELINK_CONNECTION.txt`;
- tokens/keys;
- temporary private URLs associated with a token;
- personal history databases;
- personal RAW data;
- credential-bearing logs.

---

## 15. APIs and protocol

Current chat routes:

```text
/api/auth
/api/status
/api/history
/api/send
/api/input-candidates
/api/input-preference
/ws
```

Current GAME routes:

```text
/api/game/status
/ws/game/stream
/ws/game/control
```

Do not change names, payloads, or semantics incidentally.

A protocol change requires:

1. an explicit reason;
2. coordinated Agent + App updates;
3. tests;
4. documentation;
5. a compatibility strategy when needed.

---

## 16. Installer contract

Windows Setup installs the PC Agent by default to:

```text
%LocalAppData%\KageLink PC Agent
```

Normal installation must continue to work without requiring the end user to manually install Python or development dependencies.

The installer must preserve existing data during normal upgrades.

During uninstall it may explicitly offer to remove user data.

### Bundled documentation

The `.iss` file must reference README files that actually exist in the repository.

After documentation was consolidated at repository root, the correct sources are:

```text
README.pt-BR.md
README.md
```

Do not reintroduce references to removed README files under `KageLink Installer/`.

---

## 17. APK contract

The official build entry point is:

```text
KageLink Installer\COMPILAR_APK.bat
```

The script currently:

1. validates Flutter availability;
2. validates localization catalogs;
3. creates a clean Android workspace;
4. copies sources/assets/tests/overlay;
5. runs `flutter pub get`;
6. generates localization;
7. runs `flutter analyze`;
8. builds a release APK;
9. copies the final artifact.

Current output:

```text
KageLink Installer\KageLink-v3.3.0.apk
```

Do not claim the APK was validated on a physical device unless that validation actually happened.

---

## 18. Versioning

Keep versions coherent across:

- `pubspec.yaml`;
- PC Agent version;
- installer version;
- artifact names;
- release documentation when applicable.

Do not bump a version for an unvalidated local change without an explicit release decision.

---

## 19. Required change workflow

### 1. Update context

```bash
git checkout main
git pull
```

### 2. Create a branch

Examples:

```text
fix/ic-says-classification
fix/game-focus
feat/raw-obsidian
chore/installer-build
docs/installation-guide
```

Do not develop significant changes directly on `main`.

### 3. Reproduce/define behavior

Record:

- observed behavior;
- expected behavior;
- reproducing input;
- likely responsible component;
- evidence required to accept the fix.

### 4. Locate all related implementations

Search for:

- function;
- class;
- constant;
- regex/marker string;
- route;
- model;
- writer/persistence;
- existing test;
- packaging script.

### 5. Make the smallest change

Modify only what is required.

### 6. Test

Run relevant tests and add a regression test when the bug allows it.

### 7. Review the diff

Mandatory question:

> Is any changed line unnecessary for this task?

If yes, remove it.

### 8. Use a clear commit

Examples:

```text
Fix exact Says: IC classification
Preserve GAME controls on tab exit
Fix installer documentation paths
Document complete installation flow
```

### 9. Pull Request

The PR must explain:

- problem/objective;
- root cause when applicable;
- changes;
- affected files;
- tests executed;
- pending manual validation.

### 10. Merge after appropriate validation

Bugs depending on real BYOND/Windows behavior may require manual testing before they can be considered definitively resolved.

---

## 20. Minimum tests by area

### Parser/chat

Cover at least:

```text
(*Roleplay*)                  -> IC
**Anbu** Says: test           -> IC
Uchiha, Leafos Says: hello    -> IC
Hozuki, Shin'ya Says: hello   -> IC
**Anbu** says: test           -> OOC
**Anbu** SAYS: test           -> OOC
normal OOC text               -> OOC
fragmented IC block           -> reconstructed
```

Also test mixed content and relevant false positives.

### OOC/IC sending

Validate:

- OOC found;
- IC found;
- OOC missing;
- IC missing;
- different controls;
- no silent fallback;
- game focus;
- recreated BYOND controls.

### History

Validate:

- migration;
- `channel` persistence;
- pending parser state;
- resynchronization;
- replay/duplication;
- restart.

### RAW — only when it exists in the branch

Validate:

- configuration;
- directory;
- daily file when that is the current contract;
- append;
- UTF-8;
- id/timestamp/channel;
- exact `Says:`;
- lowercase `says:` remaining OOC;
- Markdown/asterisks;
- Obsidian closed;
- replay/duplication.

### GAME

Validate:

- game open;
- game closed;
- minimized;
- maximized;
- stream;
- Full;
- Zoom;
- FPS without a growing queue;
- joystick;
- diagonals;
- A/B/C/D;
- tap;
- hold;
- multitouch;
- `focus_click`;
- tab changes;
- background state;
- disconnect while holding a key;
- no stuck keys;
- OOC/IC continuing during GAME failure.

### Flutter

When the environment is available:

```bash
flutter analyze
flutter test
```

### Python

When applicable to the branch structure:

```bash
python -m pytest
python -m compileall .
```

Never invent a test result.

---

## 21. Investigating persistent bugs

When a bug remains after editing a file, investigate in this order:

1. is that file actually executed?
2. is there another implementation of the same rule?
3. was the correct branch built?
4. did the installer package the new source?
5. is the installed EXE actually the new build?
6. is an old workspace/cache involved?
7. are App and Agent protocol-compatible?
8. does the bug occur before or after the parser?
9. does persistence use the classified `channel` or reprocess raw text?
10. does the behavior exist only in an uncommitted local build?

Do not keep applying random fixes before tracing the data flow.

---

## 22. Historical resolution — `Says:` bug

The observed bug where:

```text
**Anbu** Says: ???
**Anbu** Says: test
```

was not classified as IC was traced to the canonical parser in the official source, which originally recognized only `(* ... *)` blocks.

The official correction added the literal rule:

```python
"Says:" in line
```

The final project decision is:

```text
Says:  -> IC rule
says:  -> does not activate the rule
SAYS:  -> does not activate the rule
```

Regression tests were added for a normal speaker, `**Anbu**`, lowercase behavior, and mixed content.

This problem must no longer be described as “under investigation” in current documentation.

---

## 23. GitHub as technical memory

Important decisions must be recorded through:

- `AGENTS.md` / `AGENTS.en.md` for permanent rules;
- READMEs for installation and usage;
- commits for history;
- Pull Requests for context and validation;
- Issues for unresolved bugs/features.

External conversations can guide development, but they must not be the only memory of critical decisions.

---

## 24. Rules for AI agents

When receiving a KageLink task:

1. treat this repository as the official source;
2. read `AGENTS.md` or `AGENTS.en.md`;
3. inspect the current branch before editing;
4. search for duplicate implementations;
5. inspect existing tests;
6. preserve unrelated working behavior;
7. work on a branch;
8. keep the diff minimal;
9. test when possible;
10. clearly state validation limitations;
11. never claim a test passed without evidence;
12. never create a ZIP as a parallel source of truth;
13. do not automatically merge a change that still needs real-world validation without recording that requirement;
14. do not document a feature as “enabled” when it is absent from `main`.

### When the user says “change only X”

Treat it as a hard constraint.

Do not use the task to change Y or Z.

---

## 25. Obligation to keep documentation correct

README and Bible are part of the product.

When a change affects:

- installation;
- connectivity;
- UI;
- parser rules;
- controls;
- protocol;
- build;
- limitations;
- security;

consider whether `README.md`, `README.pt-BR.md`, `AGENTS.md`, and `AGENTS.en.md` need to change.

### Factuality rule

**Do not promise a feature in README that the current source does not contain.**

When a local build differs from `main`, document `main` as official until the implementation is committed.

---

## 26. Definition of done

A task is done when:

- the objective is clear;
- the root cause is identified when needed;
- code/documentation is in GitHub;
- the diff is limited to scope;
- relevant tests passed or limitations are recorded;
- there is no known regression;
- required documentation was updated;
- a real artifact was validated when the task depends on a build;
- there is no hidden “correct version” outside the repository.

---

# Final commandment

> **KageLink must evolve without losing what already works. GitHub is the official memory; changes are minimal, traceable, and tested; documentation describes only what the source actually supports; and no local ZIP may ever compete with the repository as the source of truth.**