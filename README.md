# KageLink 3.4.2

[Português](README.pt-BR.md) · [Development Bible](AGENTS.en.md) · [Kage Pilot](KAGE_PILOT.en.md) · [Downloads](DOWNLOAD.md)

<!-- kagelink-downloads-start -->

## ⬇️ Download

**Current stable version: KageLink 3.4.2**

| Windows | Android |
| --- | --- |
| **[Download KageLink for Windows](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Windows-Setup.exe)** | **[Download KageLink for Android](https://github.com/leafoss/KageLink/releases/latest/download/KageLink-Android.apk)** |

[Latest release and SHA-256 checksums](https://github.com/leafoss/KageLink/releases/latest)

<!-- kagelink-downloads-end -->

**KageLink** connects **Shinobi Story Online** running on Windows to an Android application for OOC/IC chat, remote game control, `Status | Inventory` viewing, and optional LeafOS/Obsidian integration.

Versions:

```text
KageLink: 3.4.2
Flutter: 3.4.2+22
```

> Android is a remote interface. The game must remain open on the computer running the PC Agent.

## Components

### PC Agent — Windows

Responsible for:

- locating `Shinobi Story Online`;
- reading BYOND chat;
- classifying OOC and IC/RP;
- persisting SQLite history and parser state;
- locating OOC and IC input fields independently;
- sending messages to the correct field;
- exposing authenticated HTTP API and WebSockets;
- providing local access and a Cloudflare Quick Tunnel;
- streaming GAME and applying allowed keys;
- streaming and controlling `Status | Inventory` through STATS;
- exporting RAW and running the LeafOS pipeline when enabled;
- providing the local experimental Kage Pilot.

### Android application

Provides:

- connection profiles;
- secure token storage;
- internal, external, and custom routes;
- OOC, IC/RP, GAME, and STATS tabs;
- synchronized history and reconnection;
- independent OOC/IC calibration;
- joystick and `ABCD`/`ZXVU` banks;
- PT-BR and EN-US.

## Installation

### Windows

1. Download `KageLink-Windows-Setup.exe`.
2. Close an older instance.
3. Run the installer.
4. Open KageLink.
5. On first launch, select PT-BR or EN-US and keep port `8765` unless another port is specifically required.

Normal upgrades preserve configuration, access key, history, and calibrations. Do not delete `config.json` or `chat_history.db` as a normal upgrade procedure.

### Android

1. Download `KageLink-Android.apk`.
2. Open the APK and allow only the installation source being used.
3. Install the application.
4. Copy the address and access key from the PC Agent.
5. Create an Android profile.

The APK and PC Agent should preferably come from the same release.

## First PC Agent launch

The wizard asks for:

- language;
- port;
- optional LeafOS enablement;
- Vault path when applicable;
- primary character when LeafOS is enabled.

The Agent automatically creates a random secure access key. Treat it as a password.

The main window presents:

- Agent, game, chat, input, and external-connection status;
- recommended external address;
- local address;
- access key;
- LeafOS character and session state;
- Ollama/Interpreter/Reviewer controls when configured.

Connection information is also stored at:

```text
%LocalAppData%\KageLink PC Agent\KAGELINK_CONNECTION.txt
```

## Create an Android connection

Provide:

- route name;
- local address, HTTPS URL, or custom address;
- access key shown by the PC Agent.

Examples:

```text
192.168.0.25:8765
https://example.trycloudflare.com
```

The `trycloudflare.com` URL may change when the tunnel restarts.

## OOC and IC/RP chat

OOC and IC are independent channels for both reading and sending.

### IC roleplay rule

Every block beginning with:

```text
(*
```

and ending at the next:

```text
*)
```

is IC/RP. Fragmented blocks remain pending until closure.

### Literal `Says:` rule

The official marker is exactly:

```text
Says:
```

IC examples:

```text
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

These do not activate the rule:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: Hello
```

The rule is intentionally case-sensitive.

### Sending

Dedicated endpoints:

```text
/api/send/ooc
/api/send/ic
```

The Agent must never silently use the other channel's input field.

Configured limit:

```text
32000 characters
```

Line breaks are normalized before writing to the game input.

### History

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

## OOC / IC calibration

BYOND may recreate HWNDs. Calibration stores geometry and enough identity information to re-locate each input.

1. Open the game.
2. Open calibration in Android.
3. Select one candidate for OOC.
4. Select a different candidate for IC.
5. Confirm both states.

One HWND must never represent OOC and IC at the same time.

## GAME

Current contract:

```text
window: Shinobi Story Online
JPEG: 960 × 540
quality: 70
target: ~10 FPS
audio: none
modes: Full | Zoom
```

Controls:

- eight-direction joystick;
- diagonals;
- tap, hold, and multitouch;
- `ABCD` and `ZXVU` banks;
- mappings persisted on Android;
- automatic key release when leaving, disconnecting, or losing safe control conditions.

Defaults:

| Button | Key |
| --- | --- |
| A | E |
| B | Space |
| C | G |
| D | V |
| Z | Z |
| X | X |
| V | V |
| U | U |

The Agent accepts only the whitelist documented in the Development Bible. GAME does not execute generic system commands.

## STATS

Exclusive target:

```text
Title: Status | Inventory
Class: #32770
Process: the same process as Shinobi Story Online
```

Features:

- independent JPEG stream at 5 FPS;
- request to open the window;
- normal tap → left click;
- long press → right click;
- normalized coordinates;
- PID, HWND, and last-frame validation.

STATS is not general desktop control.

## LeafOS / Obsidian

Integration is optional and disabled by default.

Flow:

```text
classified history
→ append-only RAW
→ Processor
→ closed session
→ Interpreter
→ pending_review
→ Memory Reviewer
→ human approval
→ Canonical Memory
```

Rules:

- RAW does not reclassify OOC/IC;
- IDs identify records;
- Processor does not reprocess IDs;
- Interpreter creates candidates, not canonical truth;
- Reviewer is the mandatory human gate;
- `memory.json` is canonical;
- `MEMORY.md` is regenerable;
- LeafOS failures remain isolated from the rest of the Agent.

Never publish personal RAW, Vault, database, tokens, private URLs, or sensitive logs.

## Kage Pilot

Kage Pilot has one public entry point:

```powershell
python kage_pilot.py dojo
```

Ten-round example:

```powershell
python kage_pilot.py dojo `
  --rounds 10 `
  --combat-seconds 120 `
  --post-combat-timeout 240 `
  --dialog-delay 5 `
  --spawn-delay 5 `
  --trainer-search-timeout 90
```

Recording and training commands also remain available through `kage_pilot.py`.

The merged baseline was validated for 10/10 rounds and preserves:

- one trainer click per round;
- dialog retry without another click;
- F12 emergency stop;
- repeated-KO protection;
- mandatory return and recovery;
- HP ≥ 90% and Chakra ≥ 50% floors;
- input release on failure and transitions.

Read [KAGE_PILOT.en.md](KAGE_PILOT.en.md) before changing this subsystem.

## Network and security

### Internal network

Use the local address when PC and phone are on the same reachable network.

### External network

Quick Tunnel provides HTTPS without normally exposing the KageLink port manually on the router.

### Access key

Sensitive routes use the KageLink key. Never publish it.

### Control boundaries

- GAME accepts allowed keys only;
- STATS accepts normalized clicks on the validated target only;
- Kage Pilot acts only against the validated game;
- fallback capture requires the exact foreground window.

## Troubleshooting

### Agent cannot find the game

- open Shinobi Story Online;
- restore the window;
- retry;
- inspect `logs\kagelink.log`.

### Android cannot connect

Check Agent, address, port, key, network reachability, and the current external URL.

### OOC or IC cannot send

Recalibrate and confirm the two fields independently.

### `**Anbu** Says: test` appears in OOC

This indicates an old build or a regression. The official rule classifies it as IC.

### RAW is missing

Check integration state, paths, enabled channel, permissions, and logs.

### STATS is missing

Open/restore `Status | Inventory` and retry.

### Startup diagnosis

```text
KageLink Installer\DIAGNOSTICAR_KAGELINK.bat
```

## Developer builds

### Android

```text
KageLink Installer\COMPILAR_APK.bat
```

Published release output:

```text
KageLink-Android.apk
```

### Windows

```text
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

Published release output:

```text
KageLink-Windows-Setup.exe
```

End users do not need Python to run the packaged Setup.

## Development

Read [AGENTS.en.md](AGENTS.en.md) before changing the project.

Principles:

- GitHub is the official source;
- use branches and PRs for significant changes;
- one canonical source per responsibility;
- historical versions belong in Git;
- tests and documentation follow contracts;
- PT-BR and EN-US are mandatory;
- record real-world validation when Windows/BYOND requires it;
- never claim a test passed unless it actually ran.

## License

Copyright © 2026 Rafael Demari Dib.

Use, modification, and compilation for the owner's personal use are permitted. Redistribution or commercial publication requires authorization. Third-party dependencies retain their own licenses.
