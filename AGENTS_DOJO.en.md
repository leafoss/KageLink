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
GET  /api/dojo/status
POST /api/dojo/start
POST /api/dojo/stop
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
```

- Starting an already running trainer returns a conflict.
- Starting without an installed runtime fails closed.
- Stop must release inputs even when the engine has already finished.

## 4. Control interlock

While `running=true`:

- manual GAME controls are blocked;
- manual control activation is blocked;
- remote game-center clicking is blocked;
- chat and STATS remain independent;
- F12 remains the local emergency stop.

This prevents the APK, Desktop and autonomous agent from issuing competing commands.

## 5. Preserved Kage Pilot v0.3j contracts

- `R` is the only normally held combat key.
- arrow keys and `H` are short conditional pulses;
- `V` and `Y` are tap-only toggles and forbidden during combat;
- every victory requires an identity-gated accepted KO;
- a repeated previous-opponent KO invalidates the target and keeps combat active;
- memory never authorizes `V` without current visual confirmation;
- combat timeout stops the loop;
- every exit, error, stop and shutdown must release keys.

Changes to these contracts require a dedicated branch, regression coverage and physical in-game validation.

## 6. Localization

Every new user-facing surface must exist in PT-BR and EN-US:

- Desktop;
- APK;
- controlled API messages;
- documentation;
- safety states and instructions.

Stable technical telemetry identifiers may remain in English for diagnostics.

## 7. Mandatory distribution gate

Before a Dojo-capable Release:

1. complete Python suite;
2. targeted Kage Pilot suite;
3. all three executables built;
4. functional `--help` for both helpers;
5. `KageLink.exe` startup smoke test;
6. Setup containing all three executables;
7. `flutter gen-l10n`, analyze and tests;
8. release APK;
9. real installed-Setup validation;
10. real APK-to-Setup validation;
11. Rafael's explicit approval before merge.

Temporary PR artifacts do not replace the official Release. The Release is rebuilt from `main` and published under stable names:

```text
KageLink-Windows-Setup.exe
KageLink-Android.apk
SHA256SUMS.txt
```

## 8. Minimum 3.5.0 physical validation

The version cannot be marked ready only because builds passed. The installed Windows product must prove:

```text
Setup installs all 3 executables
→ Desktop reports Runtime: Installed
→ start 1 round
→ dialog, combat, KO, return and recovery
→ stop from Desktop
→ start from APK
→ synchronized status and counter
→ GAME controls blocked during training
→ F12 stops and releases inputs
```

No merge or final publication should occur before this real gate.
