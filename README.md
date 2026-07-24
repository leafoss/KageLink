# KageLink

[Português (Brasil)](README.pt-BR.md)

KageLink is a companion application for **Shinobi Story Online** that connects the Windows game client to an Android interface for chat, game viewing, and remote controls.

The current `main` branch reports version **3.3.0 — GAME V1**.

## Features

- **OOC chat** with persistent history.
- **IC / RP chat** with independent history, drafts, and deterministic RP parsing.
- **GAME view** with an authenticated JPEG stream at 960×540, targeting 8–12 FPS and no audio.
- **Eight-direction joystick** mapped to the arrow keys.
- **Action buttons:** A = E, B = Space, C = G, D = V.
- Tap, hold, diagonal movement, and multitouch support.
- Internal network connection and optional external access through Cloudflare Tunnel.
- Shared authentication token for the mobile app and PC Agent.
- Automatic key release protections to prevent stuck controls.

## Architecture

KageLink is split into two main components:

- **Android app (Flutter):** mobile interface for OOC, IC/RP, and GAME.
- **Windows PC Agent (Python):** reads the Shinobi Story Online client, manages history and input, exposes the local API/WebSockets, and manages the optional Cloudflare connection.

The GAME module is isolated from chat. A GAME capture/control failure should not disable OOC/IC history, parsing, authentication, or message sending.

## GAME protocol

Main GAME routes:

```text
/api/game/status
/ws/game/stream
/ws/game/control
```

The control protocol accepts only the supported game keys. It does not provide arbitrary desktop control, command execution, macros, or unrestricted keyboard injection.

## Build the Android app

Requirements for the development machine:

- Windows
- Flutter available in `PATH`
- Android SDK configured

From `KageLink Installer/`, run:

```bat
COMPILAR_APK.bat
```

Expected output:

```text
KageLink-v3.3.0.apk
```

## Build the Windows PC Agent installer

From `KageLink Installer/`, run:

```bat
installer\CRIAR_INSTALADOR.bat
```

Expected output:

```text
installer\output\KageLink-PC-Agent-Setup-v3.3.0.exe
```

The final Windows user does not need to install Python, pip, Pillow, MSS, or the development toolchain manually.

## Repository structure

```text
KageLink/
├── README.md
├── README.pt-BR.md
└── KageLink Installer/
    ├── android_overlay/
    ├── assets/
    ├── installer/
    ├── lib/
    ├── pc_agent/
    ├── test/
    ├── COMPILAR_APK.bat
    ├── analysis_options.yaml
    ├── l10n.yaml
    └── pubspec.yaml
```

`pc_agent/requirements.txt` is a functional dependency file used by the Windows build and is intentionally kept in the repository.

## Usage and license

KageLink source code is copyright © 2026 Rafael Demari Dib.

Permission is granted to use, modify, and compile the source code for the owner's personal use. Redistribution or commercial publication requires the owner's authorization. Third-party Flutter packages remain subject to their respective licenses.
