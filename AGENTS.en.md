# KageLink — Development Bible

[Português](AGENTS.md) · [English README](README.md) · [README em Português](README.pt-BR.md)

This file is the **operational source of truth for any person or AI agent changing KageLink**.

It defines the protected contracts for the current official version, **KageLink 3.4.1**, and the workflow required to prevent regressions, divergent versions, and the old ZIP-based development process.

---

## 1. Official source

Official repository:

```text
https://github.com/leafoss/KageLink
```

### Absolute rule

**GitHub is the only official source of code.**

Do not treat any of these as the primary source:

- old ZIP files;
- Desktop copies;
- installed builds;
- isolated APKs;
- isolated EXEs;
- files pasted into chat;
- uncommitted local copies.

Correct workflow:

```text
main
  ↓
work branch
  ↓
minimal change
  ↓
tests
  ↓
diff review
  ↓
Pull Request
  ↓
real-world validation when required
  ↓
merge
```

Never use a ZIP as a substitute for Git versioning.

---

## 2. Current official version

This Bible documents:

```text
KageLink 3.4.1
Flutter: 3.4.1+20
```

Version values must stay aligned across:

- `pubspec.yaml`;
- PC Agent `APP_VERSION`;
- `COMPILAR_APK.bat`;
- `CRIAR_INSTALADOR.bat`;
- `KageLink_PC_Agent.iss`;
- artifact names;
- app version labels;
- READMEs for each release.

Do not bump the version for an unvalidated local change unless a new release decision is explicit.

---

## 3. Core philosophy

KageLink is used in a real environment.

### Primary commandment

**Do not break working behavior.**

Every change should be:

- minimal;
- localized;
- traceable;
- testable;
- compatible with unrelated working behavior.

### Forbidden during a limited task

- aesthetic refactoring;
- unnecessary file/class/route renames;
- incidental folder reorganization;
- unnecessary dependency swaps;
- unrelated UI changes;
- unrelated protocol changes;
- changing default controls without a request;
- deleting history/configuration to “fix” a bug;
- replacing an entire module when a small patch is enough;
- expanding scope because another improvement seems convenient.

When the user says **“change only X”**, treat that as a hard constraint.

---

## 4. Official 3.4.1 architecture

Main products:

1. **KageLink Android App** — Flutter.
2. **KageLink PC Agent** — Windows/Python.
3. **Windows Installer** — packages the PC Agent.
4. **LeafOS integration** — optional Agent subsystem.

Main structure:

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
    ├── lib/
    ├── pc_agent/
    ├── test/
    ├── analysis_options.yaml
    ├── l10n.yaml
    └── pubspec.yaml
```

Before editing, identify which component actually owns the observed behavior.

---

## 5. Responsibilities

### Android App

Responsible for:

- connection profiles;
- secure token storage;
- OOC UI;
- IC/RP UI;
- GAME UI;
- STATS UI;
- history presentation;
- HTTP/WebSocket connection;
- reconnect logic;
- language;
- navigation;
- user-triggered Agent calibration;
- configurable GAME controls;
- persistence of active `ABCD`/`ZXVU` bank and button mappings on Android.

### PC Agent

Responsible for:

- locating `Shinobi Story Online`;
- reading chat;
- classifying OOC/IC;
- persisting history;
- persisting parser state;
- locating OOC/IC input fields;
- sending text to the game;
- authentication;
- API/WebSockets;
- local server;
- Cloudflare Tunnel;
- GAME capture;
- GAME control;
- game-window focus;
- stuck-key protection;
- STATS capture/control;
- LeafOS RAW export;
- LeafOS Processor when enabled.

### Installer

Responsible for:

- packaging current Agent source;
- including runtime dependencies;
- including prepared/verified `cloudflared`;
- installing `KageLink.exe`;
- preserving user data during normal upgrades;
- offering deliberate user-data removal during uninstall.

**Never fix Agent behavior only in the installer. Fix Agent source, then verify the installer packages that source.**

---

## 6. One canonical source for domain logic

Domain decisions should have one canonical implementation whenever possible.

Critical example:

```text
OOC / IC classification
```

Correct conceptual flow:

```text
captured text
    ↓
ChatChannelParser
    ↓
classified message
    ├── SQLite/history
    ├── API/WebSocket
    ├── Android App
    └── LeafOS RAW
```

RAW must not independently decide whether a record is OOC or IC.

LeafOS `channel` must come from the persisted record that already passed through the canonical parser.

---

## 7. OOC / IC contract — PROTECTED RULE

### 7.1 IC roleplay blocks

Every block starting with:

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

Blocks may arrive fragmented. The parser must keep pending text until `*)` arrives.

### 7.2 IC dialogue using `Says:`

The official rule is **literal and case-sensitive**.

The only valid marker is exactly:

```text
Says:
```

These MUST be IC:

```text
**Anbu** Says: ???
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

These do NOT activate the dialogue rule:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: test
Leafos Says Hello
```

If no other IC rule applies, those examples remain OOC.

### Hard rule

**Do not make `Says:` case-insensitive without a new explicit project decision.**

This contract must remain aligned across:

- `pc_agent/chat_channels.py`;
- parser tests;
- `pc_agent/leafos.py` speaker extraction;
- LeafOS tests;
- both READMEs;
- both Bibles.

### Speaker names

Do not assume a simple name. A speaker may contain:

- spaces;
- commas;
- apostrophes;
- clan + name;
- Markdown/asterisks such as `**Anbu**`.

The parser must not require a rigid name regex to determine the channel. Channel classification depends on the canonical marker.

---

## 8. OOC / IC sending contract

OOC and IC are separate destinations.

Android 3.4.1 uses dedicated endpoints:

```text
/api/send/ooc
/api/send/ic
```

`/api/send` remains for compatibility only.

The Agent must:

1. receive the channel explicitly;
2. validate/focus the game as required;
3. re-locate input controls;
4. select only the requested channel's input;
5. reject sending when that input is unavailable;
6. never silently fall back to the other channel.

One HWND must never represent both OOC and IC simultaneously.

---

## 9. History and parser state

Default history location:

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

Preserve:

- IDs;
- timestamps;
- incoming/outgoing direction;
- `channel`;
- monitor/parser state;
- replay/resynchronization behavior.

Do not solve history bugs by deleting the database by default.

KageLink 3.4.1 uses a configured message limit of `32000`. Preserve migration from the old 400-character setting.

---

## 10. LeafOS / RAW — official 3.4.1 contract

LeafOS integration exists in the official source and is **disabled by default**.

Default configuration:

```text
enabled: false
export_ic: true
export_ooc: false
processor_interval_seconds: 30
session_idle_seconds: 900
```

User-configurable values:

- Vault path;
- RAW path;
- IC export;
- OOC export.

If a Vault exists and RAW is empty, migration may derive:

```text
<Vault>\90 - KageAgent\Raw
```

Never hardcode a personal Vault path as a universal default.

### RAW structure

```text
RAW/
├── IC/
│   └── YYYY-MM-DD.md
└── OOC/
    └── YYYY-MM-DD.md
```

Record format:

```html
<!-- kagelink-raw-begin {"id":7538,"timestamp":"...","channel":"ic","speaker":"**Anbu**"} -->
**Anbu** Says: test
<!-- kagelink-raw-end -->
```

Rules:

- append-only;
- UTF-8;
- daily file per channel;
- IDs are the primary record identity;
- restart must not duplicate records;
- changing RAW path must not replay old history into the new path;
- write failure must not advance the export cursor;
- `channel` comes from canonical history;
- `speaker` recognizes literal `Says:`;
- `(* ... *)` can naturally have `speaker: null`;
- Obsidian does not need to be open.

### Processor

When enabled/configured, the processor:

- consumes RAW;
- tracks `last_processed_id`;
- discovers participants when possible;
- creates sessions;
- closes sessions after the configured idle period;
- must not process the same IDs repeatedly;
- remains isolated from chat/GAME/STATS/tunnel.

### Privacy

Never commit:

- personal RAW;
- personal `config.json`;
- access tokens;
- private/temporary URLs;
- history database;
- sensitive logs;
- private Vault contents.

---

## 11. GAME contract — 3.4.1

Target window:

```text
Shinobi Story Online
```

Default capture contract:

```text
JPEG
960 × 540
quality 70
~10 FPS
no audio
```

View modes:

```text
full
zoom
```

GAME must remain isolated from chat.

A GAME capture/control failure must not disable:

- OOC;
- IC;
- history;
- authentication;
- LeafOS;
- STATS.

### Focus and key safety

When control is active:

- validate the game window;
- reject minimized game state;
- focus before key-down when required;
- release keys on deactivation;
- release keys on disconnect/error;
- avoid globally stuck virtual keys.

---

## 12. Configurable GAME controls

Banks:

```text
ABCD
ZXVU
```

Defaults:

```text
A -> E
B -> Space
C -> G
D -> V

Z -> Z
X -> X
V -> V
U -> U
```

Initial bank:

```text
ABCD
```

Mappings are persisted on Android.

Current protocol whitelist:

```text
A-Z
0-9
up, down, left, right
space
enter
escape
tab
shift
ctrl
alt
backspace
insert
delete
home
end
pageup
pagedown
F1-F12
```

Do not expand this list incidentally.

Because modifiers and function keys are currently allowed, any change affecting combinations must be reviewed carefully.

KageLink must not become a generic command/program execution system.

---

## 13. STATS contract — 3.4.1

STATS is independent from GAME.

Target:

```text
Title: Status | Inventory
Class: #32770
```

The target must:

- exist;
- be visible;
- belong to the same PID as Shinobi Story Online;
- match the expected title/class.

Current target rate:

```text
5 FPS
```

Allowed pointer controls:

```text
left click
right click
```

Clicks use normalized coordinates and the `window_id` from the last valid frame.

Do not turn STATS into generic desktop control.

---

## 14. API and protocol

Main chat routes:

```text
/api/health
/api/auth
/api/status
/api/history
/api/input-candidates
/api/input-preference
/api/send/ooc
/api/send/ic
/api/send        # compatibility
/ws
```

GAME:

```text
/api/game/status
/ws/game/stream
/ws/game/control
```

STATS has dedicated Agent/app stream and control protocol.

Any route, payload or semantic change requires:

1. explicit reason;
2. coordinated Agent + App update;
3. tests;
4. documentation.

---

## 15. Persistence and upgrades

Normal upgrades should preserve, when applicable:

- `config.json`;
- token;
- history;
- OOC/IC calibration;
- useful logs;
- parser state;
- LeafOS configuration.

Android persists:

- profiles;
- tokens in secure storage;
- favorites;
- active GAME bank;
- GAME mappings.

Destructive migration requires explicit authorization.

---

## 16. Mandatory change workflow

### 1. Refresh context

```bash
git checkout main
git pull
```

### 2. Create a branch

Examples:

```text
fix/ic-says-parser
fix/leafos-speaker
fix/stats-click
feat/game-controls
chore/installer-build
docs/3.4.1
```

Do not develop significant changes directly on `main`.

### 3. Reproduce the issue

Record:

- observed behavior;
- expected behavior;
- triggering input;
- responsible component;
- regression test.

### 4. Locate every related implementation

Search for:

- functions;
- constants;
- regexes;
- marker strings;
- routes;
- models;
- tests;
- documentation.

The 3.4.1 `Says:` regression demonstrated why this is mandatory: parser, tests and LeafOS speaker extraction must share the same contract.

### 5. Make the smallest change

Modify only what is necessary.

### 6. Test

Run the available test suites.

### 7. Review the diff

Mandatory question:

> Is any changed line unnecessary for this task?

If yes, remove it.

### 8. Use clear commits

Examples:

```text
Restore exact Says marker classification
Align LeafOS speaker extraction with Says marker
Document KageLink 3.4.1
```

### 9. Pull Request

Explain:

- problem;
- root cause;
- change;
- affected files;
- tests;
- manual validation still required.

### 10. Merge after validation

BYOND/Windows-dependent changes may require real manual validation before merge.

---

## 17. Minimum tests

### Parser/chat

Must cover:

```text
(*Roleplay*)                         -> IC
**Anbu** Says: test                  -> IC
**Anbu** Says: ???                   -> IC
Uchiha, Leafos Says: hello           -> IC
Hozuki, Shin'ya Says: hello          -> IC
**Anbu** says: test                  -> OOC
**Anbu** SAYS: test                  -> OOC
normal OOC text                      -> OOC
fragmented IC block                  -> preserved
fragmented Says: dialogue            -> one logical message
```

### LeafOS

Validate:

- `Says:` extracts speaker;
- `says:` does not extract speaker;
- Markdown speaker names;
- daily RAW files;
- IC/OOC separation;
- append;
- restart without duplication;
- identical text with different IDs;
- path changes;
- write error does not advance cursor;
- processor does not reprocess;
- session gap handling;
- processor failure remains isolated.

### GAME

Validate:

- game open/closed/minimized;
- Full/Zoom capture;
- joystick;
- diagonals;
- ABCD/ZXVU banks;
- custom mappings;
- mapping reset;
- hold/multitouch;
- tab switching;
- disconnect while key is pressed;
- no stuck keys.

### STATS

Validate:

- `Status | Inventory` closed/open/minimized;
- open/retry request;
- stream;
- frame dimensions;
- left click;
- right click;
- out-of-range coordinates rejected;
- mismatched `window_id` rejected;
- wrong process rejected;
- STATS failure does not affect chat/GAME.

### Python

From the appropriate PC Agent folder:

```bash
python -m unittest discover -s tests -v
python -m compileall .
```

### Flutter

```bash
flutter analyze
flutter test
```

Never claim a test passed unless it actually ran.

---

## 18. Build

### Android

```text
KageLink Installer\COMPILAR_APK.bat
```

3.4.1 output:

```text
KageLink Installer\KageLink-v3.4.1.apk
```

The script validates localization, runs `flutter analyze`, and builds the release APK.

**The Windows installer does not build the APK.**

### PC Agent

```text
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

3.4.1 output:

```text
KageLink Installer\installer\output\KageLink-PC-Agent-Setup-v3.4.1.exe
```

The builder may install build tools such as Python/Inno Setup. The final packaged end user should not need Python to run KageLink.

---

## 19. Investigating a bug that survives a patch

Check in this order:

1. Is the changed file actually imported/executed?
2. Is there another implementation of the same rule?
3. Do old tests contradict the intended contract?
4. Does another module reinterpret the data?
5. Did the installer package the new source?
6. Is the installed EXE actually the new build?
7. Is an intermediate workspace/cache stale?
8. Are APK and Agent compatible?
9. Does the problem happen before or after parsing?
10. Does RAW consume persisted `channel`, or parse text again?

Never declare a bug fixed merely because one source file changed.

---

## 20. GitHub as technical memory

Record important decisions in:

- `AGENTS.md` / `AGENTS.en.md` — permanent contracts;
- `README.pt-BR.md` / `README.md` — installation and user operation;
- commits — implementation history;
- Pull Requests — context and validation;
- Issues — unresolved bugs/features.

AI conversations may help development, but must not be the only record of a critical project decision.

---

## 21. Rules for AI agents

When working on KageLink:

1. treat this repository as the official source;
2. read `AGENTS.md` or `AGENTS.en.md`;
3. verify current `main` version;
4. inspect directly related files;
5. search for duplicated implementations;
6. preserve unrelated working behavior;
7. work on a branch;
8. keep the diff focused;
9. run available tests;
10. state validation limitations honestly;
11. update documentation when a contract changes;
12. never generate a ZIP as the “official version”;
13. do not merge a real-environment-dependent change without recording required validation.

---

## 22. Definition of done

A task is truly done when:

- the cause is identified or the change is clearly justified;
- code is in GitHub;
- scope is controlled;
- duplicated rules were checked;
- tests passed or limitations are explicitly recorded;
- no known regression remains;
- relevant documentation is current;
- real build validation is done when required;
- there is no “correct version” that exists only outside the repository.

---

# Final commandment

> **KageLink must evolve without losing what already works. GitHub is the official memory; `Says:` is an exact contract; chat, GAME, STATS and LeafOS must remain coherent, isolated and traceable.**
