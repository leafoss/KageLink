# KageLink — Dream Daemon Observer

[Português](README.pt-BR.md)

A **passive, read-only** tool for visualizing TCP traffic arriving from Dream Daemon at the `dreamseeker.exe` process.

It does not inject code, read or alter process memory, modify packets, or send game commands. Its purpose is to collect repeatable evidence and correlate protocol changes with controlled in-game events.

## What it displays

- active Dream Seeker process and TCP endpoint;
- `IN` traffic — Dream Daemon → Dream Seeker;
- `OUT` traffic — Dream Seeker → Dream Daemon;
- timestamp, payload length, TCP sequence, ACK, and stream;
- hexadecimal and ASCII payload views;
- payload entropy and printable-byte ratio;
- short SHA-256 fingerprint;
- difference from the previous packet;
- changed offsets against the previous same-length payload;
- extracted ASCII strings;
- manual event correlation;
- raw `capture.pcapng` output for Wireshark.

## Requirements

1. Windows 10 or 11.
2. Python 3.11.
3. Wireshark installed with TShark, Dumpcap, and Npcap.
4. Dream Seeker connected to the game.

Depending on Npcap configuration, start PowerShell as **Administrator**.

## Run

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\run_dream_daemon_observer.ps1
```

The launcher creates an isolated Python environment, installs only `psutil`, and starts the UI.

## Recommended first experiment

1. Open Shinobi Story Online in a safe location.
2. Start the Observer and refresh connections.
3. Select the Dream Seeker endpoint and active Ethernet or Wi-Fi interface.
4. Start capture and remain idle for five seconds.
5. Perform one isolated action.
6. Press the matching marker at the moment it occurs.
7. Repeat the same event at least ten times.
8. Stop capture and inspect the session folder.

Available markers include enemy appeared, enemy moved, player moved, attack, map changed, and custom events.

## Session output

```text
%LocalAppData%\KageLink PC Agent\data\dream_daemon_observer\YYYYMMDD_HHMMSS\
```

```text
session.json
packets.jsonl
packets.csv
markers.jsonl
event_analysis.jsonl
capture.pcapng
```

Open `capture.pcapng` in Wireshark and use **Analyze → Follow → TCP Stream** when application data is split across TCP segments.

## Interpretation boundary

A TCP packet is not necessarily one complete game message. Data may be fragmented, combined, retransmitted, compressed, encoded, encrypted, or expressed as deltas.

The first objective is therefore to find repeatable relationships, such as:

```text
Enemy enters view
→ an inbound 48-byte payload repeatedly appears
→ offsets 0x0C–0x0F change
→ related fingerprints form a stable family
```

Only after repeatable evidence exists should a separate experimental decoder be added.

## Tests

```powershell
.\run_tests.ps1
```

The tests cover payload metrics, changed offsets, same-length comparisons, direction classification, and event-only fingerprint detection.

## Version-one limits

- does not decode the BYOND protocol;
- does not claim a payload represents an entity;
- the live table displays individual TCP segment payloads;
- full reconstruction should use the PCAPNG capture;
- capture depends on TShark/Npcap and Windows permissions.
