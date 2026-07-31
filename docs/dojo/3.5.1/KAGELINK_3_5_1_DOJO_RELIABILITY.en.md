# KageLink 3.5.1 — Dojo Trainer Reliability

[Português](KAGELINK_3_5_1_DOJO_RELIABILITY.md)

## Scope

Version 3.5.1 preserves the RAW pipeline, click geometry, dialog, combat, visual return, recovery, F12, Stop and the other Dojo safety controls.

The **Dojo Trainer → Images** tab is now the absolute source of truth for the templates used to locate the Trainer.

## Correct RAW rule

Immutable RAW means that the PNG selected by the user is stored and used without visual treatment.

The active template receives no:

- resize, upscale, downscale or interpolation;
- automatic crop or padding;
- grayscale, CLAHE, equalization, brightness or contrast adjustment;
- threshold, binarization or reconstructed mask;
- blur, sharpen, denoise or morphology;
- Canny or edge detection;
- rewriting, recompression or format conversion;
- intermediate scale generation.

Immutable RAW does not prevent replacing or removing the image.

## Images-tab authority

Canonical flow:

```text
user selects PNG
→ backend validates only PNG/decoding
→ exact bytes are persisted
→ file is associated with mode 32 or 64
→ interface shows the active file
→ detector loads exactly the same file
→ matching runs at scale 1.000
```

Values 32 and 64 represent the game cell mode, not a mandatory crop dimension. A 72×73 PNG may be associated with mode 64 and remains 72×73 in the matcher.

## Replacement, removal and defaults

- `POST /api/dojo/templates/{mode}` accepts any valid PNG and preserves its exact bytes;
- `DELETE /api/dojo/templates/{mode}` removes the image, records `removed_by_user=true` and does not restore the default;
- `POST /api/dojo/templates/{mode}/restore-default` restores the default only through an explicit action;
- HTTP 409 remains only while training is active;
- PNG errors are presented in PT-BR and EN-US instead of exposing only a generic HTTP code.

Embedded templates are used only for first initialization of a mode with no persistent state. A hash difference never authorizes overwriting a user image.

## Persistence

Location:

```text
%LOCALAPPDATA%\KageLink\data\kage_pilot\templates
```

Per-mode metadata includes `user/default/none` source, real dimensions, cell mode, SHA-256, original name, date, active state and explicit removal state.

## Preserved detector

The following remain mandatory:

- original BYOND client-area capture;
- lossless PNG transport;
- full client-frame search;
- scale 1.000;
- native template pixels;
- bbox in the original client frame;
- validated bbox-to-click coordinate conversion.

KageLink.exe, KagePilotDojo.exe, KagePilotRound.exe, Anchor Monitor, API and Desktop use the same persistent storage.

## Telemetry

```text
DOJO_USER_TEMPLATE_SAVED
DOJO_ACTIVE_TEMPLATE_LOADED
DOJO_USER_TEMPLATE_REMOVED
DOJO_DEFAULT_TEMPLATE_RESTORED
DOJO_RAW_MATCH_CANDIDATE
DOJO_RAW_MATCH_CONFIRMED
```

`DOJO_RAW_TEMPLATE_MATERIALIZED reason=hash-mismatch` no longer belongs to the operational path for customized templates.

## Automated validation

Validated code head before this documentation update: `db10b7ef1ca45bc39203fbbcfed640bcb8c8a9b0`.

- Kage Pilot / KageLink 3.5 — run 181: success;
- KageLink Unified LeafOS CI — run 677: success;
- Publish KageLink Release — run 233: success;
- full Python suite and compilation: success;
- KageLink.exe, KagePilotDojo.exe and KagePilotRound.exe: build and smoke tests completed;
- Desktop smoke launch: success;
- Windows Setup, Flutter and APK: success.

## Required physical test

1. install the current preview;
2. open Dojo → Images;
3. replace the mode 64 template with a valid PNG, including 72×73;
4. confirm that HTTP 400 is not shown;
5. confirm User source, dimensions and hash in the interface;
6. start the Trainer and confirm the same hash in the log;
7. confirm scale 1.000 matching and a click attempt on the correct cell;
8. restart KageLink and confirm persistence;
9. remove the image and confirm there is no HTTP 409 caused by immutability;
10. restart and confirm the default does not return automatically;
11. restore the default only with the explicit button;
12. repeat for mode 32.

The PR remains Draft and must not be merged without Rafael's explicit authorization.
