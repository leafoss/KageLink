# KageLink 3.5.0 — Usable Dojo Trainer

[Português](KAGELINK_3_5_DOJO.md) · [Normative Bible](AGENTS_DOJO.en.md)

## Goal

Version 3.5.0 turns the repository-validated Kage Pilot v0.3j into an actually distributed feature:

```text
Windows Setup
├── KageLink.exe
├── KagePilotDojo.exe
└── KagePilotRound.exe

Desktop or APK
        ↓ authenticated API
DojoTrainingService on the PC
        ↓
Shinobi Story Online
```

The APK does not contain or execute the vision engine. It remotely controls the same service exposed by the Desktop.

## Desktop

KageLink navigation gains **Dojo Trainer** with:

- round count, including `0` for continuous execution;
- installed runtime state;
- current phase;
- current and completed rounds;
- last event or error;
- start training;
- safe stop;
- permanent F12 notice.

## Android

After connecting to the PC Agent, the application exposes two main areas:

```text
KageLink — OOC, IC/RP, GAME and STATS
Dojo — training control and telemetry
```

The Dojo screen periodically reads status and can start or stop the engine using the token already stored on Android.

## Competing-command safety

While training is active, the PC Agent rejects:

- manual GAME control activation;
- manual GAME key input;
- remote game-center clicking.

Chat and STATS remain available. The interlock is authoritative on Windows and does not rely only on disabled UI buttons.

## Isolated process and installation

`DojoTrainingService` preserves the validated isolation:

- source development uses the existing Python scripts;
- the frozen product uses `KagePilotDojo.exe`;
- the Dojo loop uses `KagePilotRound.exe` for each round;
- end users do not need external Python.

## 3.5.0 API

### Status

```http
GET /api/dojo/status
Authorization: Bearer <token>
```

### Start

```http
POST /api/dojo/start
Authorization: Bearer <token>
Content-Type: application/json

{"rounds": 10}
```

### Stop

```http
POST /api/dojo/stop
Authorization: Bearer <token>
```

Minimum safety thresholds remain protected at 90% HP and 50% Chakra.

## Distribution

The 3.5.0 Release keeps the stable links:

```text
releases/latest/download/KageLink-Windows-Setup.exe
releases/latest/download/KageLink-Android.apk
releases/latest/download/SHA256SUMS.txt
```

The Setup contains the helpers internally; users do not download them separately.

## Pre-merge gate

- Python and Kage Pilot CI;
- three Windows executables;
- helper smoke tests;
- 3.5.0 Setup;
- Flutter localization/analyze/test;
- release APK;
- real installed-Setup test;
- real Desktop → Dojo test;
- real APK → Dojo test;
- F12 and GAME interlock;
- Rafael's explicit approval.

The PR remains draft and must not be merged until the final physical tests are complete.
