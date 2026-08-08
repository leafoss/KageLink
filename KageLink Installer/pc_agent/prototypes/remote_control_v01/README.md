# KageLink Remote Control v0.3.1 — Security & Session Hardening

[Português do Brasil](README.pt-BR.md)

> Isolated prototype. This directory does not change the official KageLink runtime unless an explicit integration decision is made.

v0.3.1 reorganizes the remote-control prototype around **local consent, temporary sessions, and a hard boundary between view and control**. This revision intentionally reduces risk before the low-latency capture work planned for v0.3.2.

## Security model

The remote browser no longer relies on a permanent Host password.

```text
Remote browser
    ↓
90-second pairing request
    ↓
LOCAL Host Admin page
    ↓
[Approve control] / [Approve view] / [Deny]
    ↓
IP-bound in-memory session token
    ↓
30-second single-use peer grant
    ↓
WebRTC
```

The session token:

- is not written to `localStorage`;
- is not written to disk;
- expires after 30 minutes of inactivity by default;
- has an 8-hour absolute lifetime by default;
- is bound to the IP that requested pairing;
- is revoked when the Host disconnects the session or triggers emergency stop.

Only one active `control` session is allowed. Additional sessions may be approved as `view`.

## Local-only Admin plane

The Admin page uses a separate listener:

```text
http://127.0.0.1:8766
```

It never binds to `0.0.0.0`. An in-memory Admin token is generated on every Host start and is delivered through the local URL fragment (`#...`), so it is not sent as part of the initial HTTP request URL.

The Host can:

- approve or deny devices;
- grant `CONTROL` or `VIEW`;
- inspect active sessions;
- disconnect a session;
- inspect capture diagnostics;
- immediately disable all remote input;
- locally re-enable input when the launcher allows control.

## Local emergency stop

On the controlled PC:

```text
CTRL + ALT + F12
```

immediately:

```text
disables remote input
→ releases pressed keys/buttons
→ revokes all sessions
→ closes active WebRTC peers
```

Control can only be enabled again locally from the Host Admin page.

## Game Mode by default

`GAME MODE` reuses the canonical PC Agent window/capture modules and targets the exact configured game window, normally:

```text
Shinobi Story Online
```

Input requires the game to exist, not be minimized, and be foreground. This preserves the existing KageLink rule of targeting the game rather than accidentally capturing unrelated personal applications.

## Explicit Desktop Mode

Desktop control requires all three flags:

```text
--mode desktop --allow-control --allow-desktop-control
```

The dedicated `START_REMOTE_DESKTOP_EXTERNAL.bat` is intentionally the only bundled launcher that opts into this behavior.

## Cloudflare exposure

The external launcher binds the public/signaling server to:

```text
127.0.0.1:8765
```

and Quick Tunnel publishes HTTPS to that loopback endpoint. No public router port is required.

`CF-Connecting-IP` is trusted only when `--trust-cloudflare-proxy` is enabled and the Host bind address is loopback.

The prototype does not silently download executables. Quick Tunnel uses an existing verified KageLink `cloudflared.exe` or one available on `PATH`.

## TURN fallback

STUN is enabled by default. Restrictive networks may provide TURN through:

```text
KAGELINK_TURN_URL
KAGELINK_TURN_USERNAME
KAGELINK_TURN_CREDENTIAL
```

TURN credentials are exposed only after an authenticated session requests a peer grant.

## Input watchdog

If a control DataChannel stops sending heartbeats for 5 seconds, the Host releases all pressed keys/buttons. At 15 seconds of silence, the peer is closed.

## Latest-frame-only buffer

`FrameHub` stores only the newest frame. A slow consumer skips old frames instead of accumulating a latency queue.

This is the first low-latency foundation for v0.3.2.

## Diagnostics

Client:

- RTT;
- received FPS;
- received bitrate;
- packet loss.

Host:

- capture FPS;
- capture time;
- frame age;
- capture state.

## Mobile behavior preserved

This revision carries forward the validated mobile behavior from the previous hotfixes:

- native mobile keyboard;
- Unicode text;
- `autocapitalize="none"`;
- live IME composition;
- suffix reconciliation during predictive/autocorrect changes;
- sticky Ctrl/Alt/Shift;
- Esc/Tab/Enter/Backspace/Delete/arrows;
- tap = left click;
- long press = right click;
- drag = pointer movement;
- pinch/pan;
- 100–400% zoom;
- explicit **Release** control.

## Deliberately absent

v0.3.1 does **not** implement:

- remote shell;
- remote PowerShell;
- arbitrary command execution;
- file upload/download;
- remote clipboard;
- credential collection;
- keylogging;
- logging typed text;
- audio;
- hidden startup;
- silent persistence;
- antivirus disabling;
- UAC Secure Desktop control;
- a hidden Windows Service.

The audit log records **session events**, never keyboard/text contents.

## Setup

On the Host PC:

1. Open this directory.
2. Run:

```text
SETUP.bat
```

3. For normal external Game Mode use:

```text
START_REMOTE_EXTERNAL.bat
```

4. The Host PC opens the local Admin page.
5. On the other computer/phone, open the `https://....trycloudflare.com` address shown by the Host.
6. Select **Request connection**.
7. On the Host PC, approve the request as **Control** or **View**.

The client computer/phone needs only a modern browser.

## Launchers

### `START_REMOTE_EXTERNAL.bat`

Recommended default. Game Mode, control after local approval, Cloudflare Quick Tunnel, loopback-only Host listener.

### `START_REMOTE_LOCAL_ONLY.bat`

LAN only, no Cloudflare. The client opens:

```text
http://HOST_PC_IP:8765
```

Windows Firewall may need port 8765 allowed for the **Private** network profile only.

### `START_REMOTE_EXTERNAL_ADMIN.bat`

Runs the Game Mode Host elevated after a **local** UAC prompt. This is only useful when the game itself is elevated. UAC Secure Desktop remains outside remote control.

### `START_REMOTE_DESKTOP_EXTERNAL.bat`

Explicitly authorizes capture and input for the selected desktop. It is not the default mode.

## Tests

On Windows:

```text
RUN_TESTS.bat
```

The `Remote Control Prototype` CI verifies:

- Python syntax;
- pairing nonce rules;
- one-time session-token delivery;
- IP-bound sessions;
- single-controller enforcement;
- concurrent view sessions;
- single-use peer grants;
- expiration;
- complete revocation;
- rate limiting;
- no session secrets in the audit hook;
- JavaScript syntax;
- mobile IME compatibility layer loading.

## Known v0.3.1 limitations

- NVENC is **not** integrated yet. That belongs to v0.3.2.
- Game Mode still reuses the canonical PC Agent JPEG capture path before handing frames to WebRTC. The latency queue is removed, but capture/encode can still be substantially improved.
- Quick Tunnel remains appropriate for prototype/beta use; Named Tunnel is a later step.
- TURN must be supplied by the operator when required.
- Win32, BYOND, UAC, mobile, and NAT behavior still require physical validation before merge.

## Planned next step

```text
v0.3.2 — Low Latency Capture
```

Intended scope:

- Windows Graphics Capture where compatible;
- remove the intermediate JPEG path;
- H.264/NVENC on the RTX 3060 where supported by the selected stack;
- adaptive bitrate/resolution;
- capture → encode → network timing;
- preserve latest-frame-only behavior.
