# KageLink

[Português (Brasil)](README.pt-BR.md) · [Development Bible](AGENTS.en.md) · [Bíblia de desenvolvimento em português](AGENTS.md)

**KageLink** is a companion application for **Shinobi Story Online**. It connects the game running on a Windows PC to an Android application for OOC/IC chat, remote game viewing, and GAME controls.

The current `main` branch identifies the project as **KageLink 3.3.0 — GAME V1**.

> **Important:** KageLink is not a standalone game service. To read chat, send messages, or use GAME, **Shinobi Story Online must be running on the Windows computer where KageLink PC Agent is installed**.

---

## 1. KageLink components

KageLink is split into two products that work together.

### KageLink PC Agent — Windows

The PC Agent is installed on the computer running Shinobi Story Online. It is responsible for:

- locating the `Shinobi Story Online` window;
- reading the BYOND chat control;
- classifying OOC and IC/RP messages;
- keeping persistent SQLite chat history;
- locating separate OOC and IC input controls;
- sending messages to the correct game input;
- exposing authenticated API and WebSocket endpoints to Android;
- generating a unique access key;
- providing a local-network address;
- starting a Cloudflare HTTPS tunnel by default for remote access;
- streaming the game window to the GAME tab;
- accepting only allowed GAME controls;
- releasing pressed keys on disconnects, tab changes, and other failure states.

### KageLink Android App

The Android app provides:

- saved connection profiles;
- secure profile-token storage;
- an **OOC** tab;
- an **IC / RP** tab;
- a **GAME** tab;
- history synchronized from the PC Agent;
- real-time WebSocket updates;
- automatic reconnection;
- separate OOC and IC input calibration;
- Brazilian Portuguese and English interfaces;
- the Chakra Night visual theme;
- favorite/saved connection routes.

---

## 2. Features enabled in version 3.3.0

### 2.1 OOC chat

The **OOC** tab displays messages classified as OOC by the PC Agent.

History is stored on the Windows machine and is loaded again when Android reconnects. New messages are also delivered in real time.

When a message is sent from the OOC tab, the Agent specifically looks for the configured OOC input. If it cannot find that input, the send is blocked instead of silently using another field.

### 2.2 IC / RP chat

The **IC / RP** tab is independent from OOC and uses its own destination input.

The current parser classifies the following as IC:

1. roleplay blocks beginning with `(*` and ending at the next `*)`;
2. ordinary lines containing the literal, **case-sensitive** marker `Says:`.

Examples classified as IC:

```text
(*Uchiha, Leafos nods.*)
**Anbu** Says: test
Uchiha, Leafos Says: Hello
Hozuki, Shin'ya Says: Hello
```

Examples that **do not** activate the IC speech rule:

```text
**Anbu** says: test
**Anbu** SAYS: test
```

For the speech rule, the recognized marker is exactly `Says:` with a capital `S`.

Fragmented `(* ... *)` blocks remain buffered until the closing delimiter arrives.

### 2.3 Persistent history and real-time updates

Chat history is stored by the PC Agent at:

```text
%LocalAppData%\KageLink PC Agent\data\chat_history.db
```

The Android app loads history on connection and receives new records through WebSocket. Parser state is also persisted to reduce lost or duplicated IC blocks during restarts and resynchronization.

### 2.4 Connection profiles

The Android app can store multiple connection profiles. Each profile includes:

- a name;
- an address;
- an access key;
- an internal, external, or custom connection type;
- an optional favorite flag;
- last-used information.

The profile access key is stored with Android secure storage. Other profile metadata is stored in application preferences.

### 2.5 GAME

The **GAME** tab streams the Shinobi Story Online window to Android.

Current behavior includes:

- JPEG frames;
- `960 × 540` output;
- approximately `8–12 FPS` target;
- no audio;
- automatic landscape orientation when entering GAME;
- automatic portrait restoration when returning to OOC/IC;
- **Full** view mode;
- **Zoom** central-crop view mode;
- FPS indicator;
- approximate latency indicator;
- show/hide controls;
- eight-direction digital joystick;
- diagonal movement;
- tap, hold, and multitouch support.

Default mapping:

| Android control | PC input |
| --- | --- |
| Joystick | Arrow keys ↑ ↓ ← → |
| A | E |
| B | Space |
| C | G |
| D | V |

When GAME becomes active, Android asks the Agent to perform a focus click at the center of the captured game area. This helps return keyboard focus to Shinobi Story Online after chat interaction.

The GAME protocol accepts only:

```text
up, down, left, right, e, space, g, v
```

It does not expose generic desktop control, arbitrary macros, command execution, Alt+F4, the Windows key, or unrestricted keyboard injection.

### 2.6 Stuck-key protection

KageLink releases remote key state when appropriate, including when:

- leaving GAME;
- the Android app goes to the background;
- the control connection is lost;
- the game target is lost;
- heartbeat expires;
- the GAME session is closed.

This is designed to prevent a movement direction or action key from remaining virtually pressed on Windows.

---

# 3. Complete end-user installation

KageLink installation has two parts:

1. install **KageLink PC Agent** on Windows;
2. install the **KageLink APK** on Android.

The recommended order is to install and start the PC Agent first. That way, the address and access key are already available when the Android app is opened.

---

## 4. Install KageLink PC Agent on Windows

The expected setup file is:

```text
KageLink-PC-Agent-Setup-v3.3.0.exe
```

### Step 1 — Run Setup

Run the installer on the computer where Shinobi Story Online is played.

The installer:

- supports Brazilian Portuguese and English;
- installs for the current user;
- does not require elevated administrator privileges for the normal installation path;
- installs by default to:

```text
%LocalAppData%\KageLink PC Agent
```

- creates a KageLink Start Menu entry;
- can optionally create a desktop shortcut;
- can launch KageLink when installation finishes.

The end user does not need Python, pip, Pillow, MSS, PyInstaller, or Inno Setup to run the compiled PC Agent.

### Step 2 — First Run wizard

The first launch shows **First Run / Primeira execução**.

#### Page 1 — Language

Choose:

- `Português do Brasil`; or
- `English`.

The Agent language can be changed later in Settings.

#### Page 2 — Server port

The default port is:

```text
8765
```

This works for most installations.

If the port is already occupied, KageLink can automatically select another available port and update the local address shown in the UI.

#### Page 3 — Security

The Agent automatically generates a cryptographically random access key.

This key authenticates the Android app to the PC Agent.

**Do not publish or casually share this key.** Anyone holding both an active address and the key can attempt to authenticate to your Agent.

#### Page 4 — Secure external connection

By default, KageLink starts:

- the local server; and
- a Cloudflare Quick Tunnel using HTTPS.

This allows external access without configuring public router port forwarding for the standard setup.

#### Page 5 — Finish

After Finish, KageLink creates its configuration, starts the Agent, and displays the connection information needed by Android.

---

## 5. Understanding the PC Agent window

The Agent displays five primary status areas.

### AGENT

Shows whether the internal KageLink server is active.

### GAME

Shows whether the `Shinobi Story Online` window was located.

### CHAT

Shows whether the game chat control was located and can be read.

### INPUT

Shows whether the OOC input is currently available. IC has an independent calibration path in the Android app.

### EXTERNAL CONNECTION

Shows the state of the Cloudflare tunnel.

The window also displays the following connection values.

### Recommended external address

Example:

```text
https://example-random-name.trycloudflare.com
```

Use this when the phone is outside the same local network as the PC.

The `trycloudflare.com` address is created while the tunnel is running and can change after the external connection is restarted. Update the Android profile if it changes.

### Local address

Example:

```text
http://192.168.1.25:8765
```

Use this when the Android device and PC are on the same local network.

### Access key

This is the token required to authenticate the Android app.

The Agent provides buttons to:

- copy the address;
- copy the key;
- copy both;
- open the connection-information file;
- restart the external connection;
- retry startup;
- open logs;
- open Settings;
- open the KageLink data folder;
- exit KageLink.

The same connection values are written to:

```text
%LocalAppData%\KageLink PC Agent\KAGELINK_CONNECTION.txt
```

---

# 6. Install the APK on Android

The expected APK file is:

```text
KageLink-v3.3.0.apk
```

### Step 1 — Transfer the APK

Copy the APK to the Android device using USB, Drive, a browser, messaging, or another method you trust.

### Step 2 — Allow installation

Because this APK is installed outside Google Play, Android may ask for permission to **install unknown apps** from the application used to open the file.

Grant that permission only when you trust the KageLink build you are installing.

### Step 3 — Install

Open `KageLink-v3.3.0.apk` and complete Android's installation flow.

For an update, the new APK can normally be installed over the existing application as long as it remains compatible with the previous installation/signing identity.

### Step 4 — Open KageLink

The first screen is the route/profile hub.

---

# 7. Connect Android to the PC

Before connecting:

1. open Shinobi Story Online on Windows;
2. open KageLink PC Agent;
3. wait for the Agent to become active;
4. copy the address and access key.

On Android, create or edit a profile.

### Connection type

Choose one of:

- **Internal network** — for the PC's local address;
- **External** — for the Cloudflare HTTPS address;
- **Custom** — for another compatible address.

The type organizes the profile; the actual connection uses the address entered in the address field.

### Name

Use a convenient label, for example:

```text
Home PC
External KageLink
Laptop
```

### Address

For local network:

```text
192.168.1.25:8765
```

or:

```text
http://192.168.1.25:8765
```

For Cloudflare:

```text
https://example-random-name.trycloudflare.com
```

If `http://` or `https://` is omitted, the app automatically prefixes `http://`. For Cloudflare, copy the complete HTTPS URL displayed by the Agent.

### Access key

Paste the key exactly as shown by the PC Agent.

### Favorite

Enable Favorite to keep the profile near the top of the saved-route list.

### Establish connection

When connecting, Android:

1. authenticates the key;
2. loads history;
3. fetches Agent status;
4. saves/updates the profile;
5. opens the chat WebSocket;
6. enters the OOC/IC/GAME interface.

If the connection later drops, the app automatically retries using progressive reconnect intervals.

---

# 8. Using OOC and IC chat

The connected interface has three tabs:

```text
OOC | IC / RP | GAME
```

Tab changes use the navigation controls. The `TabBarView` intentionally disables horizontal swipe navigation so GAME cannot be accidentally dragged while using controls.

## OOC

1. open the OOC tab;
2. type the message;
3. press Send;
4. the PC Agent brings the game window to the foreground;
5. it locates the OOC input again;
6. writes the text;
7. clicks the input;
8. sends Enter.

## IC / RP

The process is the same, but the Agent uses the input configured specifically for IC.

KageLink **does not silently fall back between chat inputs**. If the IC input cannot be found while sending from IC, the message is blocked instead of being sent to OOC by mistake.

### Default message limits

The default Agent configuration uses:

- a `400` character maximum per send;
- approximately `1 second` minimum between sends.

Line breaks are normalized before text is sent to the game input.

---

# 9. Calibrating OOC and IC inputs

If Android reports that an input field was not found:

1. keep Shinobi Story Online open;
2. open the app menu;
3. choose **Calibration**;
4. refresh candidates if needed;
5. identify the correct control;
6. select **Use as OOC** or **Use as IC**.

The calibration screen displays candidate information such as:

- control index;
- `Edit` class;
- width and height;
- visibility;
- enabled state;
- relative position;
- compatibility indication.

OOC and IC must resolve to different controls. The PC Agent rejects an ambiguous configuration where both channels resolve to the same HWND.

The selected preference is persisted in the PC Agent's `config.json`.

---

# 10. Using GAME

Before entering GAME:

- the game must be running;
- its window must not be minimized;
- Android must be connected to the Agent.

When GAME is selected:

1. Android switches to landscape;
2. it opens a game-stream WebSocket;
3. it opens a separate control WebSocket;
4. it requests control activation;
5. it requests a center click in the captured game area to restore focus;
6. it starts displaying received frames;
7. joystick/action controls become available when stream and control are active.

### Full mode

Displays the complete game frame while preserving aspect ratio.

### Zoom mode

Uses the central crop defined by GAME V1.

### Hide controls

The visibility button hides the joystick and action buttons for an unobstructed view. Hiding controls also releases the currently pressed control state.

### Status indicators

The GAME top bar can display:

- LIVE/OFFLINE;
- approximate latency in milliseconds;
- received FPS;
- current view mode;
- control visibility.

### Expected unavailable states

GAME explicitly handles states such as:

- game not found;
- game minimized;
- stream unavailable;
- control disconnected.

A GAME failure is designed not to stop OOC/IC history, parsing, authentication, or chat sending.

---

# 11. Settings

## Android settings

The app Settings screen provides access to:

- the active profile/address;
- Agent operational status;
- language selection;
- input calibration;
- route/profile switching;
- application version information.

## PC Agent settings

The **Settings** button in the Windows Agent allows you to:

- switch between `pt-BR` and `en-US`;
- change the server port;
- generate a new access key.

Changing these settings restarts KageLink.

### Generating a new key

A new key invalidates the key currently stored in your Android profiles. Update those profiles with the new key before reconnecting.

---

# 12. Local network or external connection?

## Local network

Use the local address when Android and Windows are on the same trusted network.

Advantages:

- lower latency;
- no dependency on the Quick Tunnel;
- usually preferable for GAME at home.

The local address uses HTTP by default. Treat the local network as trusted and do not expose that port directly to the Internet as an improvised public endpoint.

## Cloudflare external connection

Use the external address when Android is outside the PC's local network.

The Agent starts a Quick Tunnel and presents an HTTPS `trycloudflare.com` URL.

The default flow does not require opening a public router port.

**The access key is still required. Do not publish the external URL and key together.**

---

# 13. Updating KageLink

## PC Agent-only changes

When a change affects only Python/Agent behavior, such as a parser rule:

1. build a new PC Agent installer;
2. close the running Agent;
3. run the new Setup over the existing installation;
4. start KageLink again.

The APK does not need to be rebuilt when the Android protocol did not change.

## Android-only changes

For a Flutter/UI-only change:

1. build a new APK;
2. install the updated APK on Android;
3. keep a PC Agent compatible with the protocol expected by that app.

## Coordinated changes

Changes to routes, payloads, WebSockets, or the GAME protocol can require updating both Agent and app together.

---

# 14. Uninstalling and preserving data

When uninstalling the PC Agent, Setup asks whether you also want to remove:

- access key;
- settings;
- history;
- logs.

If you choose **not** to remove user data, the data folder can remain for a future reinstall.

Do not delete `config.json` or `data/chat_history.db` as the first troubleshooting step without a backup, because doing so can remove preferences, credentials, and history.

---

# 15. Troubleshooting

## Android cannot connect

Check:

1. is `AGENT` active?
2. is the profile address correct?
3. is the port correct?
4. was the key copied without extra spaces?
5. for local access, are phone and PC on the same network?
6. for external access, is the tunnel active?
7. did the `trycloudflare.com` address change after restarting the tunnel?

## “Invalid token”

Copy the key from the Agent again. If a new key was generated, update every Android profile that used the previous key.

## Game is not located

KageLink looks for the window:

```text
Shinobi Story Online
```

Open the game before retrying.

## GAME reports a minimized game

Restore the Shinobi Story Online window. GAME does not treat a minimized window as a valid normal stream/control target.

## OOC works but IC cannot send

Open **Calibration** and configure the IC field separately. The Agent does not use OOC as a fallback for IC.

## `Says:` does not appear in IC

The official marker is literal and case-sensitive:

```text
Says:
```

with a capital `S`. Lowercase `says:` is not classified by this speech rule.

## PC Agent does not start

Logs are stored under:

```text
%LocalAppData%\KageLink PC Agent\logs
```

Important files may include:

```text
kagelink.log
startup_error.log
tunnel.log
```

The repository also includes:

```text
KageLink Installer\DIAGNOSTICAR_KAGELINK.bat
```

This script checks whether the installed executable/configuration exist and opens `startup_error.log` when available.

## Port is occupied

The Agent attempts to select another available port. Always use the address currently shown in the Agent window after an automatic port change.

---

# 16. RAW / Obsidian integration

The Development Bible contains the architectural contract intended for a RAW/Obsidian integration. However, the official 3.3.0 `main` source **does not expose RAW/Obsidian configuration in `AppConfig` and this feature should not be advertised as a standard feature of the current release**.

When the integration officially enters `main`, it must:

- reuse canonical OOC/IC classification;
- write without requiring Obsidian to be open;
- keep its destination configurable;
- preserve UTF-8 and raw text;
- never commit private RAW files to GitHub.

---

# 17. Build from source

The official source is:

```text
https://github.com/leafoss/KageLink
```

Clone it:

```bash
git clone https://github.com/leafoss/KageLink.git
cd KageLink
```

Before building, update your checkout:

```bash
git checkout main
git pull
```

## 17.1 Build the Android APK

Development requirements:

- Windows;
- Flutter available in `PATH`;
- Android SDK configured;
- Internet access when dependencies need to be downloaded.

Enter:

```text
KageLink Installer
```

Run:

```bat
COMPILAR_APK.bat
```

The script:

1. checks Flutter;
2. validates all four localization catalogs;
3. recreates a clean Android workspace;
4. copies `lib`, assets, tests, and Android overlays;
5. runs `flutter pub get`;
6. runs `flutter gen-l10n`;
7. runs `flutter analyze`;
8. builds the release APK;
9. copies the final APK to the project folder.

Expected output:

```text
KageLink Installer\KageLink-v3.3.0.apk
```

**The Windows installer does not build the APK.** `COMPILAR_APK.bat` is the Android build entry point.

## 17.2 Build the Windows PC Agent installer

From `KageLink Installer`, run:

```bat
installer\CRIAR_INSTALADOR.bat
```

The build script:

1. locates a suitable Python installation;
2. can install Python through `winget` in the development environment when necessary;
3. creates an isolated `.builder_venv`;
4. installs Agent dependencies and PyInstaller;
5. prepares and validates the bundled `cloudflared` executable;
6. builds `KageLink.exe` with embedded Python;
7. locates or installs Inno Setup when possible;
8. builds the final Setup executable.

Expected output:

```text
KageLink Installer\installer\output\KageLink-PC-Agent-Setup-v3.3.0.exe
```

The end user receiving this final Setup does not need the build environment used to create it.

---

# 18. Repository layout

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

---

# 19. Security and privacy

- Do not publish your installed `config.json`.
- Do not share your access key.
- Do not publish `KAGELINK_CONNECTION.txt` without removing the key.
- Do not expose the local HTTP port directly to the Internet unless you fully understand the security implications.
- GAME control is restricted to an explicit key whitelist.
- The Agent validates the target game window before applying controls.
- Android profile tokens are kept in secure storage.
- Normal installer updates are designed to preserve existing user data.

---

# 20. Development and contributions

Before modifying KageLink, read:

- [AGENTS.en.md — Development Bible](AGENTS.en.md)
- [AGENTS.md — Bíblia de Desenvolvimento](AGENTS.md)

The project's central rule is:

> **Do not break working behavior. Changes must be minimal, traceable, tested, and kept in GitHub — never in a parallel ZIP that becomes a competing source of truth.**

---

# 21. License

KageLink source code copyright © 2026 Rafael Demari Dib.

The source code may be used, modified, and compiled for the owner's personal use. Redistribution or commercial publication requires the owner's authorization. Third-party Flutter packages remain subject to their respective licenses.