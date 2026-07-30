# KageLink 3.5.0

[Português](README.pt-BR.md) · [Downloads](DOWNLOAD.md) · [Development Bible](AGENTS.en.md) · [Kage Pilot](KAGE_PILOT.en.md)

## Download

| Windows | Android |
| --- | --- |
| **[Download KageLink for Windows](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Windows-Setup.exe)** | **[Download KageLink for Android](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Android.apk)** |

[Open the Release and SHA-256 checksums](https://github.com/leafoss/KageLink/releases/latest) · [Quick guide](DOWNLOAD.md)

**KageLink** connects **Shinobi Story Online** running on Windows to a Desktop interface and an Android app. Version 3.5.0 includes OOC/IC chat, GAME, STATUS, optional LeafOS integration, and the installed **Dojo Trainer**.

```text
KageLink: 3.5.0
Flutter/Android: 3.5.0+23
```

> Android is a remote interface. Capture, vision, decisions, and keyboard commands run only in the PC Agent.

## Components

### Windows

The Setup installs:

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

- `KageLink.exe`: Desktop, Agent, API, chat, GAME, STATUS, and LeafOS integration.
- `KagePilotDojo.exe`: isolated training loop.
- `KagePilotRound.exe`: isolated round runtime.

End users do not need to install Python.

### Android

The application provides:

- saved connection profiles;
- secure token storage;
- OOC and IC/RP;
- remote GAME;
- remote STATUS;
- Dojo control and telemetry;
- reconnect behavior;
- PT-BR and EN-US.

## Quick installation

### Windows

1. Download `KageLink-Windows-Setup.exe`.
2. Close any older KageLink instance.
3. Run the Setup.
4. Choose PT-BR or EN-US.
5. Open KageLink and copy the displayed address and access key.

The default port is `8765`. KageLink creates a secure key and, by default, a temporary Cloudflare HTTPS route.

Normal upgrades preserve configuration, history, access key, and Dojo templates.

### Android

1. Download `KageLink-Android.apk`.
2. Install the APK.
3. Create a profile using the address and key displayed on Windows.
4. Use the local address on the same network or the HTTPS URL for external access.

## OOC and IC/RP chat

OOC and IC are separate channels for both reading and sending.

```text
/api/send/ooc
/api/send/ic
```

The Agent must never silently use the other input as fallback.

### Protected IC rule

Every `(* ... *)` block is IC/RP.

The dialogue marker is literal and case-sensitive:

```text
Says:
```

```text
**Anbu** Says: test     → IC
**Anbu** says: test     → does not activate the rule
```

## GAME

GAME streams the specific game window and accepts only validated keys.

- JPEG capture at `960 × 540`;
- approximately 10 FPS;
- Full and Zoom modes;
- joystick and `ABCD` / `ZXVU` banks;
- heartbeat and stuck-key protection;
- release on disconnect, screen change, or unsafe conditions.

GAME cannot execute programs, scripts, URLs, or system commands.

## STATUS

Expected target:

```text
Title: Status | Inventory
Class: #32770
```

The Agent validates that the window belongs to the same game process before streaming or clicking. Tap sends left click; long press sends right click.

## Dojo Trainer

Dojo Trainer runs on Windows and can be controlled from Desktop or Android.

```text
Desktop/Android
→ authenticated API
→ KageLink.exe
→ KagePilotDojo.exe
→ KagePilotRound.exe
→ Shinobi Story Online
```

### Trainer templates

The user registers independent images for 32×32 and 64×64 game modes:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates\
```

Installed training cannot start without at least one valid template. Normal upgrades preserve those templates.

### Safety

- exactly one Trainer click per round;
- dialog retries never repeat that click;
- F12 is the emergency stop;
- minimum recovery HP: 90%;
- minimum recovery Chakra: 50%;
- manual GAME controls are blocked during training;
- every exit releases inputs.

Details: [KAGE_PILOT.en.md](KAGE_PILOT.en.md) and [AGENTS_DOJO.en.md](AGENTS_DOJO.en.md).

## LeafOS / Obsidian

LeafOS integration is optional and disabled by default.

```text
classified history
→ append-only RAW
→ Processor
→ session
→ Interpreter
→ Memory Reviewer
→ human approval
→ Canonical Memory
```

A LeafOS failure must not stop chat, GAME, STATUS, tunnel, or Dojo.

Never publish personal RAW, private Vault contents, history databases, tokens, temporary URLs, or personal configuration.

## Network and security

- use the local address while PC and phone share a network;
- use the HTTPS route for external access;
- treat the access key as a password;
- do not publish tokens or private URLs;
- sensitive endpoints and WebSockets require the Bearer Token.

## Diagnostics

### Game not found

- open Shinobi Story Online;
- restore the window when minimized;
- retry discovery;
- inspect `logs\kagelink.log`.

### OOC or IC cannot send

Open calibration and select both input controls independently.

### Dojo does not start

Confirm:

- installed runtime availability;
- at least one valid 32×32 or 64×64 template;
- game open and visible;
- no training already active;
- logs and the last code shown on the Dojo screen.

## Developers

Read [AGENTS.en.md](AGENTS.en.md) before changing the project.

### Python tests

```powershell
cd "KageLink Installer\pc_agent"
python -m unittest discover -s tests -v
python -m compileall .
```

### Kage Pilot

```powershell
python kage_pilot.py dojo --show-config
python -m unittest discover -s tests -p "test_kage_pilot*.py" -v
```

### Flutter

```powershell
cd "KageLink Installer"
flutter pub get
flutter gen-l10n
flutter analyze
flutter test
```

### Windows build

```text
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

### Android build

```text
KageLink Installer\COMPILAR_APK.bat
```

## Canonical documentation

- [Development Bible](AGENTS.en.md)
- [Dojo normative rules](AGENTS_DOJO.en.md)
- [Kage Pilot](KAGE_PILOT.en.md)
- [Interpreter](AGENTS_INTERPRETER.en.md)
- [Memory Reviewer](LEAFOS_MEMORY_REVIEWER.en.md)
- [Desktop](LEAFOS_DESKTOP.en.md)
- [Downloads](DOWNLOAD.md)

## License

Source code copyright © 2026 Rafael Demari Dib. Personal use, modification, and compilation are allowed for the owner. Redistribution or commercial publication requires authorization. Third-party dependencies retain their own licenses.
