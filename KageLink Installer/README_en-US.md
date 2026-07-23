# KageLink 3.3.0 — Chat + Game V1

KageLink 3.3.0 preserves the validated 3.2.0 chat system and adds an isolated **GAME** module. The app reuses the same server, domain, Cloudflare tunnel, connection profile, and token. A missing or failed game stream does not stop OOC/IC reading, parsing, history, or message sending.

## GAME tab

The app now has **OOC**, **IC / RP**, and **GAME** tabs. GAME switches Android to landscape and opens two independent authenticated WebSockets:

- `/ws/game/stream` for 960×540 JPEG frames at a target of 10 FPS;
- `/ws/game/control` for the whitelisted keyboard state.

Returning to a chat tab restores portrait orientation, releases every game key, and keeps chat state and drafts.

The approved visual reference is included at `docs/Idea.png`.

## Controls

The transparent joystick maps to the arrow keys and supports eight directions. Fixed action mapping:

- A → E
- B → Space
- C → G
- D → V

All controls support tap and hold, real multitouch, and no toggle mode. Only `up`, `down`, `left`, `right`, `e`, `space`, `g`, and `v` are accepted.

## Stream modes

- **Full screen:** preserves the source aspect ratio and letterboxes when necessary.
- **Zoomed:** fixed central 16:9 crop at approximately 2×. Character detection is intentionally outside V1.

The exact Windows title is `Shinobi Story Online`. The agent captures a suitable render child when available and falls back to the top-level client area. A minimized or missing window produces an app status without affecting chat.

## Build

Run `COMPILAR_APK.bat` on Windows with Flutter and Android SDK to create `KageLink-v3.3.0.apk`.

Run `installer\CRIAR_INSTALADOR.bat` to create `installer\output\KageLink-PC-Agent-Setup-v3.3.0.exe`. The final user does not need Python or development dependencies.

See `RELATORIO_TESTES_3.3.0.md` for validation scope and required Windows/game acceptance tests.
