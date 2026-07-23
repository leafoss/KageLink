# KageLink

[Português (Brasil)](README.pt-BR.md)

KageLink is a companion application for **Shinobi Story Online** that connects the Windows game client to an Android mobile interface. Version **3.3.0 — GAME V1** preserves the validated OOC/IC chat system and adds an isolated GAME module for remote viewing and controls.

## What KageLink does

KageLink provides three mobile tabs:

- **OOC** — out-of-character chat.
- **IC / RP** — roleplay/in-character chat with independent history and drafts.
- **GAME** — live game image and remote controls.

The GAME module is intentionally isolated from chat. If the game is closed, minimized, unavailable, or the game stream fails, OOC/IC reading, parsing, history, authentication, and message sending remain available.

## Version 3.3.0 highlights

- Authenticated game stream at **960×540**, JPEG, target **8–12 FPS**, no audio.
- Two view modes: **Full screen** and **Zoomed** (~2× central 16:9 crop).
- Transparent eight-direction joystick mapped to the arrow keys.
- Action buttons with tap, hold, and multitouch:

| Button | Key |
| --- | --- |
| A | E |
| B | Space |
| C | G |
| D | V |

- Automatic landscape orientation in GAME and portrait restoration when returning to chat.
- Exact target window: `Shinobi Story Online`.
- Automatic key release on disconnect, backgrounding, tab exit, heartbeat timeout, game loss, or agent shutdown.
- Existing OOC/IC protocol preserved from 3.2.0.

The approved visual reference is kept at `KageLink Installer/docs/Idea.png`.

## Architecture

KageLink reuses the same server, connection profile, Cloudflare tunnel, and authentication token for chat and GAME while keeping the new GAME routes separate.

### Existing chat routes

- `/api/auth`
- `/api/status`
- `/api/history`
- `/api/send`
- `/api/input-candidates`
- `/api/input-preference`
- `/ws`

### GAME routes

- `/api/game/status`
- `/ws/game/stream`
- `/ws/game/control`

The Windows PC Agent locates the game window and attempts to capture a suitable render child. When necessary, it falls back to the top-level client area. The design avoids streaming the full desktop.

## Security model

The GAME control protocol accepts only this whitelist:

```text
up, down, left, right, e, space, g, v
```

Arbitrary keyboard commands, text injection, Alt+F4, Windows key, Ctrl+Esc, macros, and general desktop control are outside the protocol.

Game input is sent only after locating and validating the `Shinobi Story Online` window. The control layer tracks pressed keys to avoid duplicate key-down events and missed key-up events.

## Repository layout

```text
KageLink/
├── README.md
├── README.pt-BR.md
├── LICENSE
└── KageLink Installer/
    ├── COMPILAR_APK.bat
    ├── DIAGNOSTICAR_KAGELINK.bat
    ├── android_overlay/
    ├── assets/
    ├── docs/
    ├── installer/
    ├── lib/
    ├── pc_agent/
    ├── test/
    ├── analysis_options.yaml
    ├── l10n.yaml
    └── pubspec.yaml
```

## Build the Android app

Development requirements:

- Windows
- Flutter available in `PATH`
- Android SDK configured

From `KageLink Installer/`, run:

```bat
COMPILAR_APK.bat
```

The script creates a clean Android workspace, copies the project sources, generates localizations, runs Flutter analysis, and builds:

```text
KageLink-v3.3.0.apk
```

## Build the Windows PC Agent installer

From `KageLink Installer/`, run:

```bat
installer\CRIAR_INSTALADOR.bat
```

The build process creates an isolated environment, installs the agent build dependencies, packages Python and required libraries with PyInstaller, includes Cloudflared, and builds the installer with Inno Setup.

Output:

```text
installer\output\KageLink-PC-Agent-Setup-v3.3.0.exe
```

The final user does **not** need Python, Pillow, MSS, pip, or development tools installed manually.

## Install / update 3.3.0

### Android

1. Run `COMPILAR_APK.bat` on the development machine.
2. Install `KageLink-v3.3.0.apk` over the current app.
3. Keep using the saved server/profile/token.

### Windows PC Agent

1. Close KageLink on Windows.
2. Run `installer\CRIAR_INSTALADOR.bat` on the development machine.
3. Install `KageLink-PC-Agent-Setup-v3.3.0.exe` over the previous version.
4. Existing configuration, token, history, logs, and connection data are preserved by the installer.
5. Open Shinobi Story Online and then KageLink.

The 3.3.0 APK requires the 3.3.0 PC Agent for GAME features. Chat remains based on the previous compatible protocol, but older agents do not expose the new GAME endpoints.

## GAME behavior

### Capture

- Target window title: `Shinobi Story Online`.
- Output: `960 × 540`.
- Target rate: `8–12 FPS` (10 FPS nominal target).
- Binary JPEG frames.
- No audio.
- Latest-frame behavior; no intentional large frame queue.

### View modes

**Full screen** preserves aspect ratio and uses letterboxing when necessary.

**Zoomed** uses a fixed central 16:9 crop at approximately 2×. Character detection and free zoom controls are intentionally outside GAME V1.

### Controls

The joystick outputs digital arrow-key states in eight directions. Diagonals use two simultaneous arrow keys. Action buttons support tap and continuous hold, and multitouch allows movement and action buttons at the same time.

There is no toggle mode.

## Validation status

The 3.3.0 source package recorded the following automated/static validation results:

- **26 Python tests passed**.
- 17 existing chat/parser/history/migration tests remained passing.
- 7 GAME protocol tests covered whitelist enforcement, arbitrary-key rejection, multitouch state, heartbeat, and allowed modes.
- 2 image tests covered 960×540 output, aspect-preserving letterbox, and the central zoom crop.
- Python `compileall` passed.
- Four ARB localization files were valid with **178 equivalent translatable keys**.
- **157 localization references** were checked.
- Relative Dart imports and lexical delimiter checks passed.
- Flutter, PC Agent, and installer versions were aligned to 3.3.0.

### Windows acceptance tests

The source-generation environment did not provide Windows, Flutter/Android SDK, a running Shinobi Story Online client, Windows PyInstaller, or Inno Setup. Therefore the following should be validated on the target Windows environment:

1. Normal, maximized, and full-screen game window capture.
2. Missing, minimized, closed, and reopened game states.
3. Correct useful-area selection.
4. Real 8–12 FPS behavior and absence of growing delay.
5. Full screen and Zoomed modes.
6. Four directions and four diagonals.
7. A=E, B=Space, C=G, D=V.
8. Tap, hold, and multitouch.
9. Leaving GAME/backgrounding/disconnecting while holding a control.
10. No stuck keys.
11. OOC/IC remaining operational during GAME failures.
12. Upgrade installation preserving user configuration and history.

## Release history

### 3.3.0 — GAME V1

Added the isolated GAME tab, authenticated 960×540 stream, Full screen/Zoomed modes, eight-direction joystick, A/B/C/D controls, input whitelist, heartbeat and stuck-key protection, exact game-window targeting, new GAME routes, Pillow/MSS packaging, and GAME protocol/image tests.

### 3.2.0 — OOC and IC/RP chat

Added independent OOC and IC/RP tabs, deterministic RP block parsing, multiline/fragment reconstruction, SQLite parser state, channel-aware history/API/WebSocket models, independent unread/draft/scroll state, safer IC input discovery, and automated parser/migration tests.

### 3.1.1

Fixed GUI logging in PyInstaller builds without a console and preserved the custom KageLink logging system.

### 3.1.0

Separated internal-agent and Cloudflare Tunnel states, made startup/retry idempotent, added continuous `/api/health` checks, improved game detection, and added window snapshots to logs.

### 3.0.4

Fixed temporary Cloudflared executable handling and retained SHA-256, MZ-header, and version validation.

### 3.0.3

Updated the Cloudflared 2026.7.2 SHA-256 validation and added executable/header/version checks.

### 3.0.2

Improved backend/tunnel startup, automatic port handling, internal health checks, diagnostics, retry/log controls, and Cloudflared packaging.

### 3.0.1

Fixed first-run visibility and startup error handling, improved focus/centering behavior, and hardened shutdown/mutex handling.

### 3.0.0

Introduced the final single-agent model: Tkinter UI, FastAPI server, managed Cloudflare tunnel, automatic configuration and connection file generation, single-instance mutex, masked logs, and a single Windows installer experience.

## Project rule

KageLink is a working project. Changes should be scoped and minimal: do not refactor or modify unrelated working behavior unless the requested change requires it.

## License

See [`LICENSE`](LICENSE).