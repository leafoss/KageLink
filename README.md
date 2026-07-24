# KageLink 3.4.1

[Português (Brasil)](README.pt-BR.md) · [Development Bible](AGENTS.en.md) · [Bíblia de desenvolvimento](AGENTS.md)

**KageLink** is a companion application for **Shinobi Story Online**. It connects the game running on a Windows PC to an Android app for chat, remote game controls, remote `Status | Inventory` viewing, and optional **LeafOS/Obsidian** integration.

The official version documented here is **KageLink 3.4.1**. The Flutter application is versioned as `3.4.1+20`.

> KageLink requires Shinobi Story Online to be running on the Windows PC where the PC Agent is installed. The Android app is a remote interface; it does not run the game by itself.

---

## 1. Components

### KageLink PC Agent — Windows

The PC Agent is installed on the same computer that runs Shinobi Story Online. It:

- locates the `Shinobi Story Online` window;
- reads BYOND chat;
- classifies messages as OOC or IC/RP;
- keeps persistent SQLite history;
- locates OOC and IC input fields independently;
- sends text to the correct game input;
- exposes authenticated HTTP API and WebSockets;
- creates and preserves an access key;
- provides a local-network address;
- starts a Cloudflare HTTPS tunnel by default;
- streams the game window to the GAME tab;
- receives allowed GAME controls;
- locates and streams `Status | Inventory` to the STATS tab;
- supports left/right clicks in STATS;
- exports RAW records to LeafOS/Obsidian when enabled;
- runs the LeafOS processor in the background when configured;
- isolates chat, GAME, STATS and LeafOS so a local failure should not take down the whole Agent.

### KageLink Android App

The Android app provides:

- saved connection profiles;
- secure token storage;
- internal, external or custom connection routes;
- **OOC** tab;
- **IC / RP** tab;
- **GAME** tab;
- **STATS** tab;
- synchronized history;
- live WebSocket updates;
- automatic reconnection;
- independent OOC/IC input calibration;
- configurable GAME controls;
- two action-button banks: `ABCD` and `ZXVU`;
- Brazilian Portuguese and English;
- Chakra Night visual theme.

---

## 2. End-user installation

Installation has two parts: the **Windows PC Agent** and the **Android APK**.

### 2.1 Install the PC Agent

Use the Setup matching the app version:

```text
KageLink-PC-Agent-Setup-v3.4.1.exe
```

1. Close an older KageLink instance if it is running.
2. Run the Setup.
3. Choose English or Brazilian Portuguese.
4. Keep the default `%LocalAppData%\KageLink PC Agent` install location unless you have a specific reason to change it.
5. The desktop shortcut is optional.
6. Finish installation and open KageLink.

Normal upgrades are designed to preserve configuration, access key, history and user data. During uninstall, the installer asks whether those data should also be removed.

### 2.2 First Agent run

A first-run wizard is shown.

#### Language

Choose:

- `English`; or
- `Português do Brasil`.

The language can be changed later in **Settings**.

#### Port

Default port:

```text
8765
```

Most users do not need to change it.

If the configured port is busy, the Agent searches for another available port and saves it. Always use the address currently displayed by the Agent when configuring the phone.

#### Access key

KageLink automatically creates a cryptographically random access key used by the Android app.

Treat it as a password. Do not publish it and do not commit it to GitHub.

Regenerating the key invalidates profiles that still contain the previous key.

#### External connection

By default, the Agent starts a **Cloudflare Quick Tunnel** over HTTPS. This allows remote use without manually exposing the KageLink port on the router.

The `trycloudflare.com` URL is temporary and may change after the tunnel restarts. Update the Android external profile when it changes.

### 2.3 PC Agent main window

The main window reports status for:

- **AGENT** — internal backend;
- **GAME** — Shinobi Story Online detection;
- **CHAT** — chat capture;
- **INPUT** — message input availability;
- **EXTERNAL CONNECTION** — Cloudflare tunnel.

It also displays:

- **Recommended external address**;
- **Local address**;
- **Access key**.

Useful actions include:

- **Copy address**;
- **Copy key**;
- **Copy both**;
- **Open connection info**;
- **Restart connection**;
- **Try again**;
- **Open logs**;
- **Settings**;
- **Open folder**;
- **Exit KageLink**.

Connection details are also written to:

```text
%LocalAppData%\KageLink PC Agent\KAGELINK_CONNECTION.txt
```

### 2.4 Install the Android APK

Use:

```text
KageLink-v3.4.1.apk
```

1. Copy the APK to the Android device.
2. Open it.
3. If Android requests permission to install from that source, allow only the source used to open the APK.
4. Install KageLink.
5. Open the app.

The APK and PC Agent should preferably come from the same KageLink release.

---

## 3. Create an Android connection

Create a route/profile on the first screen.

### Profile name

This is only a human-readable label, for example:

```text
Home PC
Local network
External KageLink
```

### Connection type

Available categories:

- **Internal network**;
- **External route**;
- **Custom route**.

The category organizes the profile. The actual connection is defined by the address.

### Internal address

Use the local address shown by the PC Agent, for example:

```text
192.168.0.25:8765
```

The phone and PC must be able to reach each other on the network.

### External address

Use the HTTPS URL shown by the Agent, for example:

```text
https://example.trycloudflare.com
```

This is the normal choice when the phone is outside the PC's local network.

### Access key

Paste the key shown by the PC Agent exactly.

The token is stored in Android secure storage. Other profile metadata is stored in application preferences.

### Saved and favorite profiles

Successful profiles can be reused. Favorites are kept at the top of the route list.

---

## 4. OOC and IC/RP chat

KageLink treats OOC and IC as separate channels for both reading and sending.

### 4.1 OOC

The OOC tab displays messages classified as OOC by the Agent.

When sending from OOC, the app uses the OOC-specific endpoint and the Agent searches only for the configured OOC input field. If it cannot find that field, sending is rejected instead of silently using the IC field.

### 4.2 IC / RP

The IC tab receives two forms of content.

#### Roleplay blocks

Any block starting with:

```text
(*
```

and ending at the next:

```text
*)
```

is IC.

Example:

```text
(*Uchiha, Leafos lowers his head.*)
```

If a block arrives fragmented across multiple chat reads, the parser buffers it until the closing delimiter is received.

#### Dialogue using `Says:`

The official rule is **literal and case-sensitive**.

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

These examples **do not** activate the IC dialogue rule:

```text
**Anbu** says: test
**Anbu** SAYS: test
Uchiha, Leafos sAyS: Hello
```

They follow the OOC path unless they are inside a `(* ... *)` block.

> This rule is intentionally strict. Do not make `Says:` case-insensitive without a new explicit project decision.

### 4.3 Sending messages

KageLink 3.4.1 raises the configured Agent message limit to `32000` characters. Before sending, line breaks are normalized to spaces because the destination is a game input control.

Dedicated endpoints:

```text
/api/send/ooc
/api/send/ic
```

Legacy `/api/send` remains for compatibility.

### 4.4 History

Persistent history is stored in:

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

The Android app loads history on connection and receives new records over WebSocket.

---

## 5. OOC / IC input calibration

Shinobi Story Online may expose several Windows `Edit` controls. KageLink must not assume one control represents both channels.

In the Android app:

1. connect to the Agent;
2. open the menu;
3. choose **Open input scan / Calibrate input**;
4. keep Shinobi Story Online open on the PC;
5. select one candidate for **OOC** and a different candidate for **IC**;
6. confirm both channels are reported as located.

Candidate `002` is the known initial IC reference, but full geometry is saved after calibration. BYOND can recreate controls with new HWND values, so matching does not rely only on a fixed window handle.

The same HWND must never represent both OOC and IC simultaneously.

---

## 6. GAME tab

GAME streams the Shinobi Story Online window.

Current behavior:

- window-specific capture;
- JPEG output;
- `960 × 540` output resolution;
- default JPEG quality 70;
- approximately 10 FPS target;
- no audio;
- **Full** view mode;
- **Zoom** view mode;
- FPS indicator;
- approximate latency indicator;
- eight-direction digital joystick;
- diagonal movement;
- tap, hold and multitouch;
- show/hide controls;
- automatic key release when leaving GAME, disconnecting or losing safe control conditions.

When GAME becomes active, the app requests game focus and the Agent can issue the focus click used by the control flow.

### 6.1 Action-button banks

KageLink 3.4.1 provides two banks:

```text
ABCD
ZXVU
```

Defaults:

| App button | Default PC key |
| --- | --- |
| A | E |
| B | Space |
| C | G |
| D | V |
| Z | Z |
| X | X |
| V | V |
| U | U |

The initial bank is `ABCD`. Active bank and mappings are persisted on Android.

### 6.2 Configure GAME controls

Open:

```text
Settings → GAME controls
```

You can change mappings and reset one bank or all defaults.

Keys currently accepted by the protocol:

```text
A-Z
0-9
UP / DOWN / LEFT / RIGHT
SPACE
ENTER
ESC
TAB
SHIFT
CTRL
ALT
BACKSPACE
INSERT
DELETE
HOME
END
PAGE UP / PAGE DOWN
F1-F12
```

The Agent rejects key identifiers outside this whitelist. Because modifiers and function keys are included, configure mappings deliberately.

---

## 7. STATS tab

STATS is isolated from GAME and targets the Shinobi Story Online window:

```text
Status | Inventory
```

Expected Windows class:

```text
#32770
```

The Agent verifies that the target belongs to the same process as the game.

Current features:

- independent JPEG stream;
- `5 FPS` target;
- FPS and latency indicators;
- retry/open request when the window is unavailable;
- normal tap → left click;
- long press → right click;
- normalized coordinates relative to the displayed image;
- target-window ID validation before clicks.

STATS is not a general desktop remote-control surface. It is limited to the validated `Status | Inventory` window from the Shinobi Story Online process.

---

## 8. LeafOS / Obsidian

LeafOS integration is an official 3.4.1 feature but is **disabled by default**.

### 8.1 Enable LeafOS

In the PC Agent:

1. open **Settings**;
2. enable **Enable LeafOS integration**;
3. choose the LeafOS Vault directory;
4. choose or enter the RAW output directory;
5. choose **Export IC**;
6. choose **Export OOC** if desired;
7. save; KageLink restarts so the backend uses the new configuration.

Default configuration:

```text
LeafOS: disabled
Export IC: enabled
Export OOC: disabled
```

If a Vault is configured and RAW is left empty, the configuration can derive:

```text
<Vault>\90 - KageAgent\Raw
```

The RAW location remains user-configurable and must never be hardcoded to a personal Vault path.

### 8.2 RAW structure

The exporter creates:

```text
RAW/
├── IC/
│   └── YYYY-MM-DD.md
└── OOC/
    └── YYYY-MM-DD.md
```

Each append-only record contains a technical envelope:

```html
<!-- kagelink-raw-begin {"id":7538,"timestamp":"...","channel":"ic","speaker":"**Anbu**"} -->
**Anbu** Says: test
<!-- kagelink-raw-end -->
```

`channel` comes from the same canonical chat classification used by history and the Android app. RAW does **not** run a second OOC/IC parser.

`speaker` extraction follows the same literal `Says:` rule. `(* ... *)` roleplay blocks can naturally have `speaker: null`.

Obsidian does not need to be open for RAW files to be written.

### 8.3 LeafOS processor

When LeafOS is enabled, IC export is enabled, and Vault/RAW paths exist, the Agent can start the LeafOS processor.

Current defaults:

```text
processor interval: 30 seconds
session idle close: 900 seconds / 15 minutes
```

The processor persists state so it does not repeatedly process the same IDs and creates session/participant structures inside the Vault.

Processor failures are deliberately isolated from chat, GAME, STATS and the tunnel.

### 8.4 Privacy

Never commit the following to GitHub:

- personal RAW logs;
- personal `config.json`;
- history database;
- access tokens;
- private temporary URLs;
- sensitive logs;
- private Vault content.

---

## 9. PC Agent settings

The current Settings dialog supports:

- UI language;
- server port;
- access-key regeneration;
- LeafOS enable/disable;
- Vault path;
- RAW path;
- IC export toggle;
- OOC export toggle.

Relevant changes restart KageLink so backend, tunnel and optional modules all use the same configuration.

---

## 10. Android settings

The app lets you:

- change language;
- inspect current route and Agent state;
- open OOC/IC calibration;
- configure GAME controls;
- switch route/profile;
- view application version.

GAME mappings are Android-side preferences. OOC/IC calibration is saved by the PC Agent.

---

## 11. Network and security

### Internal network

Prefer the local address when PC and phone are on the same reachable network.

### External network

Cloudflare Quick Tunnel provides HTTPS and avoids manual router port exposure for normal external access.

### Token

Sensitive API routes and app WebSockets use the KageLink access key. Treat it as a password.

### Remote control

GAME accepts only key identifiers present in the current whitelist. STATS accepts only normalized left/right clicks against the validated `Status | Inventory` window.

---

## 12. Troubleshooting

### Agent cannot find the game

- open Shinobi Story Online;
- make sure the game is not minimized;
- use **Try again**;
- inspect `logs\kagelink.log`.

### Android app cannot connect

Check:

1. PC Agent is running;
2. address is correct;
3. port is correct;
4. token is correct;
5. phone can reach the PC or tunnel;
6. the external URL has not changed.

### OOC or IC cannot send

Open calibration and verify both input fields independently.

### `**Anbu** Says: test` appears in OOC

That indicates a regression or an old Agent build. Under the official rule, this message is IC. Verify that the installed PC Agent was built from a revision containing the exact `Says:` fix.

### RAW is not created

Check:

- LeafOS enabled;
- RAW path configured;
- channel export enabled;
- write permissions;
- Agent logs.

### STATS does not appear

- keep the game running;
- reopen the STATS tab;
- use the retry/open action;
- verify `Status | Inventory` can be opened in the game;
- do not keep that window minimized.

### Startup diagnosis

The repository includes:

```text
KageLink Installer\DIAGNOSTICAR_KAGELINK.bat
```

It checks `%LocalAppData%\KageLink PC Agent`, looks for `KageLink.exe`, and opens `startup_error.log` when present.

---

## 13. Updating an installation

1. obtain or build the new Setup;
2. close the old KageLink Agent;
3. install the new Setup over the existing installation;
4. reopen the Agent;
5. verify address, key and settings;
6. update the APK when that release also changes the Android app.

Do not delete `config.json` or `chat_history.db` as a normal upgrade procedure.

---

## 14. Build the Android APK — developers

Requirements:

- Windows;
- Flutter in `PATH`;
- configured Android SDK.

From:

```text
KageLink Installer
```

run:

```bat
COMPILAR_APK.bat
```

The script:

1. validates localization files;
2. creates a temporary Android workspace;
3. copies source/assets/configuration;
4. runs `flutter pub get`;
5. runs `flutter gen-l10n`;
6. runs `flutter analyze`;
7. builds a release APK;
8. copies the final artifact.

Output:

```text
KageLink Installer\KageLink-v3.4.1.apk
```

**The Windows installer does not build the APK.**

---

## 15. Build the Windows installer — developers

Run:

```bat
KageLink Installer\installer\CRIAR_INSTALADOR.bat
```

The builder:

1. finds Python 3.11 or tries to install it through `winget`;
2. creates an isolated build virtual environment;
3. installs dependencies and PyInstaller;
4. prepares/verifies `cloudflared`;
5. builds `KageLink.exe` with embedded Python runtime;
6. finds/installs Inno Setup when required;
7. compiles the final Setup.

Output:

```text
KageLink Installer\installer\output\KageLink-PC-Agent-Setup-v3.4.1.exe
```

The **end user** does not need Python to run the packaged KageLink. Python is part of the development/build process, not normal use of the final Setup.

---

## 16. Main repository structure

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

---

## 17. Development rules

Read [AGENTS.en.md](AGENTS.en.md) before changing KageLink.

Core principles:

- GitHub is the official source;
- do not use ZIP files as the primary development source;
- work through branches;
- keep changes minimal and traceable;
- preserve unrelated working behavior;
- update tests and documentation when a contract changes;
- never claim a test passed unless it actually ran.

---

## 18. License

KageLink source code copyright © 2026 Rafael Demari Dib.

Permission is granted to use, modify and compile the source code for the owner's personal use. Redistribution or commercial publication requires the owner's authorization. Third-party dependencies remain subject to their respective licenses.
