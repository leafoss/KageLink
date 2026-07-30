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

The APK does not contain or run the vision engine. It remotely controls the same service used by the Desktop.

## Desktop

The canonical KageLink navigation order is:

```text
Overview
Memory
Connection
Dojo Trainer
Settings
```

`Settings` must always remain the final item. New pages are inserted before it.

The **Dojo Trainer** page contains:

- round count, including `0` for continuous execution;
- installed runtime status;
- current phase;
- current round and completed total;
- latest event or error;
- independent template upload for 32×32 mode;
- independent template upload for 64×64 mode;
- preview and removal for each template;
- start training;
- stop safely;
- permanent F12 notice.

## Trainer templates

KageLink 3.5.0 does not use a packaged image as the primary authority. The user supplies the crop that works in their installation and selects the matching game mode.

Canonical persistence:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates\
├── dojo_trainer_32.png
├── dojo_trainer_64.png
└── templates.json
```

Properties:

- accepts PNG, JPEG, WebP and BMP through the UI;
- validates and normalizes the file to PNG;
- preserves templates through normal updates;
- loads both modes simultaneously when both exist;
- selects the accepted visual candidate with the highest score;
- rejects strong cross-mode ambiguity;
- does not start the installed runtime without at least one valid template;
- retains the old source-tree calibration only for local Python diagnostics.

## Android

After connecting to the PC Agent, the app offers two primary areas:

```text
KageLink — OOC, IC/RP, GAME and STATUS
Dojo — training control and telemetry
```

The Dojo screen polls state and can start or stop the engine using the token already stored on Android. Visual calibration belongs to the PC Desktop, which has access to the local file and game capture.

## Competing-command safety

While training is active, the PC Agent rejects:

- manual GAME control activation;
- manual GAME key input;
- remote game-center clicking;
- Desktop template replacement or deletion.

Chat and STATUS remain available. The block is authoritative on Windows and does not depend only on disabled UI controls.

## Isolated process and installation

`DojoTrainingService` preserves the validated isolation:

- in the repository, it uses the existing Python scripts;
- in the frozen program, it uses `KagePilotDojo.exe`;
- the Dojo loop uses `KagePilotRound.exe` for each round;
- end users do not need an external Python installation;
- helpers read templates from the user profile, outside the executable.

## 3.5.0 API

### Query state

```http
GET /api/dojo/status
Authorization: Bearer <token>
```

### Query templates

```http
GET /api/dojo/templates
Authorization: Bearer <token>
```

### Upload template

```http
POST /api/dojo/templates/64
Authorization: Bearer <token>
Content-Type: application/json

{
  "filename": "trainer.png",
  "image_base64": "..."
}
```

The same contract accepts `/32`.

### Delete template

```http
DELETE /api/dojo/templates/32
Authorization: Bearer <token>
```

### Start

```http
POST /api/dojo/start
Authorization: Bearer <token>
Content-Type: application/json

{"rounds": 10}
```

Without a valid template, it fails closed with `DOJO_TRAINER_TEMPLATE_REQUIRED`.

### Stop

```http
POST /api/dojo/stop
Authorization: Bearer <token>
```

The protected minimum thresholds remain 90% HP and 50% Chakra.

## Distribution

Release 3.5.0 continues to use stable links:

```text
releases/latest/download/KageLink-Windows-Setup.exe
releases/latest/download/KageLink-Android.apk
releases/latest/download/SHA256SUMS.txt
```

Setup contains the helpers internally; users do not download them separately. Templates do not need to be packaged.

## Pre-merge gate

- Python and Kage Pilot CI;
- three Windows executables;
- helper smoke tests;
- Setup 3.5.0;
- Settings as the final menu item;
- 32×32 and 64×64 template upload and persistence;
- real detection in 32×32 mode;
- real detection in 64×64 mode;
- Flutter localization/analyze/test;
- release APK;
- real installed-Setup test;
- real Desktop → Dojo test;
- real APK → Dojo test;
- F12 and GAME blocking;
- Rafael's explicit approval.

Until the final physical tests are complete, the PR remains draft and must not be merged.
