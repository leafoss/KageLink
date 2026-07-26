# KageLink · LeafOS Desktop

[Português (Brasil)](LEAFOS_DESKTOP.md) · [README](README.md) · [Development Bible](AGENTS.en.md)

**KageLink · LeafOS Desktop** brings the Shinobi Story Online Agent and the LeafOS memory workflow into the same `KageLink.exe`. End users no longer need PowerShell, Python module commands, or a separately launched Memory Reviewer.

## Normal user flow

```text
Open KageLink.exe
        ↓
confirm Primary Character
        ↓
open Shinobi Story Online
        ↓
play normally
        ↓
KageLink records chat + history + RAW
        ↓
Processor organizes the session
        ↓
Finalize session and review
        ↓
local Interpreter (Ollama / qwen3:14b)
        ↓
Memory Reviewer
        ↓
Approve / Edit + approve / Reject
        ↓
Canonical Memory
```

Android remains optional. It is still the remote interface for OOC, IC/RP, GAME, STATS and character configuration, but LeafOS no longer depends on the Android app being opened to know the user's active character.

## One application, separated modules

The user sees one program:

```text
KageLink.exe
```

Internally the responsibilities stay separated:

```text
Chat Reader / Parser
HistoryStore
RAW Exporter
Processor
Interpreter
Memory Reviewer
Canonical Memory
GAME
STATS
Tunnel
```

This is a user-experience unification, not a merger of domain responsibilities. Isolation, testability and traceability remain intact.

## Primary Character

When LeafOS is enabled, the Desktop displays the current character. If no character is configured, KageLink asks for one and the Processor refuses to create a new ambiguous session.

Each new session stores its own `primary_character`.

Changing characters performs this order first:

```text
sync RAW
    ↓
process pending messages
    ↓
close previous session
    ↓
record character_changed
    ↓
activate new character
```

This prevents two user-controlled identities from being mixed into one session.

## Session closing

The 15-minute idle rule remains, but it is now an automatic fallback rather than the normal session-ending mechanism.

A session can close because of:

- **Finalize session and review**;
- Primary Character change;
- normal KageLink exit, including X/Alt+F4;
- persistent Shinobi Story Online window closure;
- idle timeout;
- recovery of a session left open by an abnormal termination.

Closed sessions record:

```text
close_reason
closed_cleanly
closed_at
primary_character
```

Current reasons:

```text
manual
character_changed
agent_shutdown
game_closed
idle_timeout
unclean_shutdown_recovery
```

## KageLink shutdown order

During a normal exit, session preservation has priority over infrastructure teardown:

```text
final chat read
        ↓
history
        ↓
RAW sync
        ↓
Processor
        ↓
close session
        ↓
save state
        ↓
stop backend/tunnel
        ↓
close KageLink
```

If safe finalization fails, the UI reports the failure before a forced exit can be chosen.

## Recovery after abrupt termination

No process can run shutdown code after a power loss, BSOD or `taskkill /F`.

On the next launch, KageLink checks the Processor state for a leftover `open_session`. When found, it closes that orphaned session as:

```text
close_reason: unclean_shutdown_recovery
closed_cleanly: false
```

Before closing it, the exporter attempts to synchronize history that had already been persisted.

## Shinobi Story closed

The Desktop watches the Agent's existing game-online state. After the game has been online, a continuous absence of roughly 10 seconds is treated as game shutdown and can close the active LeafOS session with `game_closed`.

The small grace period avoids turning momentary detection glitches into session boundaries.

## Interpreter inside KageLink

The Interpreter keeps the same semantic contract:

```text
closed session
    ↓
LeafOSInterpreter
    ↓
Interpretation Bundle
status: pending_review
```

It is still forbidden from creating canonical memory automatically.

The difference is that the user can now run it from the **Memory** screen or through **Finalize session and review**. The CLI remains available only for development and diagnostics.

## Ollama

The default remains:

```text
qwen3:14b
http://127.0.0.1:11434
```

The Memory screen reports:

- Ollama installed or missing;
- server online/offline;
- `qwen3:14b` available or missing.

The UI provides actions to:

- install Ollama through `winget` when available;
- start `ollama serve` without PowerShell;
- run `ollama pull qwen3:14b` without PowerShell.

The model is not bundled inside `KageLink.exe`, avoiding a multi-gigabyte installer.

## Memory Reviewer

The Reviewer preserves the human gate:

```text
Interpreter candidate
        ↓
validate evidence through RAW
        ↓
Approve
Edit + approve
Reject
        ↓
Canonical Memory only after explicit human approval
```

In the packaged build, **Open Memory Reviewer** launches the Reviewer through the same `KageLink.exe`. The user never needs to find Python or run a command.

## Canonical Memory

The official computable source remains:

```text
<Vault>/60 - Canonical Memory/memory.json
```

The human-readable projection remains:

```text
<Vault>/60 - Canonical Memory/MEMORY.md
```

`MEMORY.md` remains derived and is not a second canonical source.

## Desktop navigation

The main navigation is:

```text
Overview
Memory
Connection
Settings
```

**Overview** shows services, character, active session and finalization actions.

**Memory** shows Ollama, model availability, closed sessions, interpretations and Reviewer pending counts.

**Connection** keeps external/local addresses, access key and tunnel controls.

**Settings** keeps language, port and LeafOS configuration.

The visual identity follows the approved LeafOS Memory Reviewer language: dark green surfaces, leaf accents and PT-BR/en-US support.

## Safety contract

The unified experience does not change these rules:

1. RAW remains append-only evidence.
2. Processor organizes; it does not perform narrative inference.
3. Interpreter produces candidates, never canonical truth.
4. Reviewer requires valid evidence.
5. Permanent memory requires explicit human action.
6. GAME/STATS/chat/tunnel remain isolated from LeafOS failures.
7. OOC does not become a semantic RP session in the current Processor.
8. Normal end-user operation requires no PowerShell.

## Build

PyInstaller now uses `unified_launcher.py` as the entrypoint and packages the Reviewer/LeafOS assets into `KageLink.exe`.

CI runs:

```text
full Python unittest suite
compileall
Flutter analyze
Flutter test
PyInstaller package smoke build
KageLink.exe artifact verification
```

The preview executable is published by the workflow as:

```text
KageLink-unified-preview
```
