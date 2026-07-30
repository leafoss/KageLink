# AGENTS_3_5.en.md — KageLink 3.5.0 normative addendum

[Português](AGENTS_3_5.md) · [Main Bible](AGENTS.en.md) · [Runtime](AGENTS_RUNTIME.en.md) · [Kage Pilot](KAGE_PILOT.en.md)

This addendum complements `AGENTS.en.md`. The detailed contracts in the main Bible remain valid. When old version or architecture references conflict with the current product, this addendum governs KageLink 3.5.0.

## 1. Version and official source

```text
KageLink 3.5.0
Version source: RELEASE_VERSION
```

`RELEASE_VERSION` is the only human-edited version source. The PC Agent, Flutter, Inno Setup, builders, workflows, `/api/health`, artifacts, and release text must remain aligned through automated validation.

## 2. Installed product

The official Windows distribution includes:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

- `KageLink.exe` hosts Desktop, API, and public state.
- `KagePilotDojo.exe` isolates the between-round loop.
- `KagePilotRound.exe` isolates one round.
- Helpers are not competing implementations; they route to canonical boundaries.
- The official installation must not depend on installed Python or loose `.py` scripts.

## 3. Canonical Kage Pilot surface

```text
kage_pilot.py
kage_pilot_loop.py
KAGE_PILOT.md
KAGE_PILOT.en.md
```

New integrations must not import versioned filenames directly.

Internal `v03*` files still required by the physically validated engine are temporary compatibility layers. Do not remove them until imports, specs, workflows, and tests are migrated to canonical names, the complete suite is green, and real validation is repeated.

## 4. Future organization

- One responsibility has one canonical name.
- Versions belong to Git, tags, releases, and changelog entries.
- Do not create new files named with `v03x`, dates, `final`, `new`, `hotfix`, or equivalents.
- Incremental documents must be consolidated into the canonical document for the major update.
- History removed from the active tree remains available through Git and PRs.

## 5. 32×32 and 64×64 templates

Dojo Trainer templates are supplied by the user and persisted under:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates
```

Protected rules:

- each mode has independent data and metadata;
- normal update/reinstall preserves templates;
- missing valid templates blocks startup;
- an embedded template must not become the primary executable authority;
- stale matches or isolated memory never authorize input;
- Desktop and Android expose the same public service state.

## 6. Failures and retries

Normative outcomes:

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

`NOT_FOUND`, `TIMEOUT`, and `FAILED` are not automatically fatal.

Retries repeat only the failed stage. A confirmed one-shot action must not be repeated while waiting for its response.

For the Dojo:

```text
1 Trainer click
→ 1 initial wait/check
→ up to 3 additional waits/checks
→ final failure ends only the round when safe
```

## 7. Safety and isolation

- manual GAME input is blocked during autonomous training;
- F12 releases inputs and stops the loop;
- Dojo failure does not stop chat, history, STATS, or LeafOS;
- every subprocess has an owner, timeout, exit code, terminate/kill policy, and cleanup;
- no transition may leave a key or mouse button pressed.

## 8. Persisted state

Each state declares a policy:

- fail closed: evidence, identity, sessions, cursors, and canonical memory;
- quarantine and rebuild: proven reconstructible cache;
- backup and defaults: recoverable configuration with a warning.

Never silently treat existing invalid identity, session, or cursor state as empty.

## 9. Protocols and languages

PT-BR and EN-US are mandatory.

API and WebSocket surfaces should prefer stable codes such as:

```text
DOJO_TRAINER_TEMPLATE_REQUIRED
GAME_NOT_FOUND
FOREGROUND_FAILED
INVALID_TOKEN
```

The presentation layer translates codes. Services/controllers must not create new hardcoded visible prose when localization exists.

## 10. Release gate

Before publishing:

- complete Python suite;
- compileall/py_compile;
- Flutter gen-l10n, analyze, and tests;
- build/smoke of `KageLink.exe`;
- build/`--help` of `KagePilotDojo.exe` and `KagePilotRound.exe`;
- Windows Setup;
- APK;
- version parity;
- preservation of user data/templates;
- physical validation proportional to the change.

Never claim a test or validation passed unless it was actually executed.
