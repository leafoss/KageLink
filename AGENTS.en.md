# KageLink — Development Bible

[Português](AGENTS.md) · [Runtime and organization](AGENTS_RUNTIME.en.md) · [Kage Pilot](KAGE_PILOT.en.md) · [PT-BR README](README.pt-BR.md) · [EN-US README](README.md)

This file is the **operational source of truth for every person or AI agent changing KageLink**.

It governs the official code published on `main`, including Android, PC Agent, Installer, LeafOS, and Kage Pilot. The specialized chapters linked above have equal normative force within their scopes.

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
- isolated APK or EXE files;
- files pasted into chat;
- runtime logs;
- virtual environments;
- local configuration;
- uncommitted local copies.

Correct workflow:

```text
main
  ↓
work branch
  ↓
minimal coherent change
  ↓
tests
  ↓
diff review
  ↓
Pull Request
  ↓
real-world validation when required
  ↓
explicit merge
```

Never use a ZIP as a substitute for Git.

---

## 2. Official version

The release version is defined by:

```text
RELEASE_VERSION
```

This is the only human-edited version source. Flutter, Installer, backend, `/api/health`, labels, artifacts, workflows, and READMEs must stay synchronized through generation or automated tests.

The `main` state reviewed after PR #16 contains release `3.4.2` and a validated Kage Pilot Dojo. Manual references to `3.4.1` must not remain as the current state.

Do not bump the version for an unvalidated local change without an explicit release decision.

---

## 3. Core philosophy

KageLink is used in a real environment.

### Primary commandment

**Do not break working behavior.**

Every change must be:

- minimal;
- localized;
- traceable;
- testable;
- reversible when possible;
- compatible with unrelated working behavior.

### Forbidden during a limited task

- aesthetic refactoring;
- dependency changes without a functional reason;
- unrelated UI or protocol changes;
- changing default mappings without a request;
- deleting history/configuration to “fix” a bug;
- replacing a whole module when a small patch is enough;
- expanding scope for convenience;
- creating another versioned copy when the canonical file can be updated.

When the user says **“change only X”**, treat it as a hard constraint.

A broad reorganization is allowed only when explicitly requested, as with this Kage Pilot consolidation, and must have an inventory, tests, rollback, and a dedicated PR.

---

## 4. Official architecture

Main products:

1. **KageLink Android App** — Flutter.
2. **KageLink PC Agent** — Windows/Python.
3. **Windows Installer** — packages the PC Agent.
4. **LeafOS integration** — optional Agent subsystem.
5. **Kage Pilot** — local perception, combat, and Dojo-training subsystem.

Canonical structure:

```text
KageLink/
├── AGENTS.md
├── AGENTS.en.md
├── AGENTS_RUNTIME.md
├── AGENTS_RUNTIME.en.md
├── KAGE_PILOT.md
├── KAGE_PILOT.en.md
├── README.md
├── README.pt-BR.md
├── RELEASE_VERSION
└── KageLink Installer/
    ├── installer/
    ├── lib/
    ├── pc_agent/
    ├── test/
    └── pubspec.yaml
```

The packaged composition, workers, failures, persistence, windows, and organization rules are defined in `AGENTS_RUNTIME.en.md`.

Before editing, identify which component actually owns the observed behavior.

---

## 5. Responsibilities

### Android App

Responsible for:

- connection profiles;
- secure token storage;
- OOC and IC/RP;
- GAME and STATS;
- history presentation and reconciliation;
- HTTP/WebSocket and reconnect logic;
- PT-BR/EN-US language support;
- navigation and calibration;
- configuration/persistence of `ABCD`/`ZXVU` controls.

### PC Agent

Responsible for:

- locating `Shinobi Story Online`;
- reading and classifying chat;
- persisting history and parser state;
- locating OOC/IC input fields;
- sending text;
- authentication, API, and WebSockets;
- local server and Cloudflare Tunnel;
- GAME capture/control;
- STATS capture/control;
- focus and stuck-input protection;
- LeafOS RAW/Processor/Interpreter/Reviewer when enabled;
- stable services exposed to Kage Pilot.

### Installer

Responsible for:

- packaging the current source;
- including dependencies and verified `cloudflared`;
- installing `KageLink.exe`;
- preserving data during normal upgrades;
- offering deliberate data removal during uninstall.

**Never fix an Agent bug only in the installer.**

### Kage Pilot

Responsible for:

- perception and tracking inside the game;
- target selection;
- trainer acquisition;
- deterministic Dojo flow;
- combat, KO, return, and recovery;
- telemetry and emergency stop.

The complete contract is in `KAGE_PILOT.en.md`.

---

## 6. One canonical source of logic

Domain decisions must have one canonical implementation.

OOC/IC example:

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

RAW must not decide the channel again.

For Kage Pilot:

```text
stable entry point
    ↓
canonical service
    ↓
internal modules by responsibility
```

Do not create `v03l`, `v03m`, or equivalent as a new official source. Update the canonical name and preserve history through Git.

---

## 7. OOC / IC contract — PROTECTED RULE

### IC roleplay blocks

Every block beginning with `(*` and ending at the next `*)` is IC/RP. Fragmented blocks stay pending until the closing delimiter arrives.

### IC dialogue using `Says:`

The rule is **literal and case-sensitive**.

Valid marker:

```text
Says:
```

These must be IC:

```text
**Anbu** Says: ???
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

These do not activate the rule:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: test
Leafos Says Hello
```

Do not make `Says:` case-insensitive without a new explicit decision.

The rule must stay aligned across parser, tests, speaker extraction, LeafOS, READMEs, and both Bibles.

Speaker names may contain spaces, commas, apostrophes, clan names, and Markdown. Classification depends on the marker, not a rigid name regex.

---

## 8. OOC / IC sending

Dedicated endpoints:

```text
/api/send/ooc
/api/send/ic
```

`/api/send` remains for compatibility.

The Agent must:

1. receive the channel explicitly;
2. validate/focus the game;
3. re-locate controls;
4. select only the requested channel;
5. reject when the control is unavailable;
6. never silently fall back to the other channel.

One HWND must never represent both OOC and IC.

---

## 9. History and parser state

Default history path:

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

Preserve:

- IDs;
- timestamps;
- direction;
- channel;
- monitor/parser state;
- replay/resync behavior;
- ID monotonicity relative to the Vault.

Do not delete the database as a default fix.

Current message limit: `32000`. Preserve migration from old 400-character configuration.

---

## 10. LeafOS / RAW

The integration is optional and disabled by default.

Default configuration:

```text
enabled: false
export_ic: true
export_ooc: false
processor_interval_seconds: 30
session_idle_seconds: 900
```

Never hardcode a personal Vault path.

### RAW

```text
RAW/
├── IC/YYYY-MM-DD.md
└── OOC/YYYY-MM-DD.md
```

Rules:

- append-only;
- UTF-8;
- IDs are identity;
- no duplication after restart;
- write failure does not advance the cursor;
- channel comes from canonical history;
- speaker extraction uses literal `Says:`;
- Obsidian does not need to be open.

### Memory flow

```text
immutable RAW
→ Processor
→ closed session
→ Interpreter
→ pending_review Bundle
→ Memory Reviewer
→ Canonical Memory
```

Permanent rules:

- Interpreter produces candidates;
- promotion requires human approval;
- Reviewer does not alter RAW/Processor/Bundle;
- evidence must trace back to RAW;
- `memory.json` is canonical;
- `MEMORY.md` is a derived view;
- invalid canonical JSON blocks writes.

Persistence and corruption policies are defined in `AGENTS_RUNTIME.en.md`.

---

## 11. GAME and STATS

Target window:

```text
Shinobi Story Online
```

Default GAME stream:

```text
JPEG
960 × 540
quality 70
~10 FPS
no audio
```

Modes:

```text
full
zoom
```

GAME remains isolated from chat, LeafOS, and STATS. Capture/control failure must not stop unrelated modules.

STATS works with `Status | Inventory` and must validate HWND, PID, title, class, expected frame, and client coordinates before a click.

The common window/input gate in `AGENTS_RUNTIME.en.md` also applies to Kage Pilot.

---

## 12. Security

- random token and timing-safe comparison;
- Android tokens stored in secure storage;
- no token or sensitive query-string logging;
- `cloudflared` pinned by version and SHA-256;
- GAME/Kage Pilot keyboard input limited to approved keys;
- inputs released on error/disconnect/shutdown;
- generic screen fallback only after validating and focusing the correct window;
- automation must not execute arbitrary programs, URLs, or system commands received from users.

---

## 13. PT-BR and EN-US

All product text must support `pt-BR` and `en-US`.

- UI uses localization catalogs;
- controllers/services return codes, not localized prose;
- API/WebSocket uses stable technical codes;
- user documentation has an equivalent counterpart;
- IDs, JSON fields, and technical codes are not translated;
- missing translation must not break functionality.

---

## 14. File organization

The active tree is not a historical archive.

### Canonical rule

- one public file per stable entry point;
- internal modules by responsibility;
- no attempt suffix on new official implementations;
- tests by contract, not temporary version;
- old reports remain in Git history, not as current manuals;
- disposable scripts leave the tree once absorbed by automated tests;
- replaced versions are removed after updating imports, workflows, and tests.

“One Kage Pilot” means one coherent surface, not a thousand-line monolith.

Every consolidation must happen on a dedicated branch and pass the complete suite.

---

## 15. Tests

Run the risk-proportional set before declaring completion.

### Python

```powershell
cd "KageLink Installer\pc_agent"
python -m unittest discover -s tests -v
python -m compileall .
```

### Flutter

```powershell
cd "KageLink Installer"
flutter pub get
flutter gen-l10n
flutter analyze
flutter test
```

### Packaging

Validate build, smoke launch, and installer when entry points, dependencies, or release metadata are affected.

### Kage Pilot

Run the targeted suite, full PC Agent suite, and real Windows/BYOND validation when changes affect perception, input, windows, timing, KO, or Dojo behavior.

Never claim a test that was not run.

---

## 16. Definition of done

A task is complete only when:

- scope was checked;
- the active source was identified;
- unrelated contracts were preserved;
- proportional tests were executed;
- cleanup and failure behavior were considered;
- PT-BR/EN-US documentation was updated;
- version remains coherent;
- no sensitive information was published;
- pending real validation is stated;
- the active tree did not gain another redundant snapshot;
- the change is in a reviewable branch/PR.

When uncertain, preserve current behavior, record the uncertainty, and return to the Bibles before editing.
