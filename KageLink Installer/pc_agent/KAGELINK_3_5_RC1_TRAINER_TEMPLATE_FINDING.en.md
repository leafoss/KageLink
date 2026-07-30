# KageLink 3.5.0 RC1 — Trainer-template packaging failure

**Date:** 2026-07-29  
**PR:** #18  
**Affected RC:** commit `1f3e608406f0dc6006adb433a244a7109afc31f4`

## Physical result

The Setup, Desktop, API, APK and remote Dojo start worked. During initial trainer acquisition, however, the character remained in the bounded search and never visually confirmed the sprite.

## Confirmed cause

The v0.3b record states that the old embedded reference did not reach a sufficient score against the real game capture. The reliable detector therefore used a locally calibrated image saved at:

```text
data/kage_pilot/dojo_leader_template.png
```

That directory is ignored by Git. The calibrated file present on the computer used for source-tree validation therefore never entered GitHub.

`KagePilotDojo.spec` and `KagePilotRound.spec` collect the Python/OpenCV dependencies but do not include `data/kage_pilot/dojo_leader_template.png` in `datas`. In the installed executable, `CalibratedDojoLeaderDetector` cannot find the local template and silently falls back to the older embedded reference.

The search consequently never receives two visual confirmations above the threshold and keeps issuing bounded search pulses until timeout.

## Mandatory RC2 correction

1. recover the original calibrated template from the validation computer;
2. version a canonical copy suitable for distribution;
3. include the file in both PyInstaller helpers;
4. preserve support for a future local override;
5. emit explicit template-source telemetry;
6. fail closed before walking when only the incompatible fallback is available;
7. add a gate that runs the packaged helpers and verifies the distributed template can be found and decoded;
8. generate a new RC2 Setup and repeat physical validation.

## State

RC1 is not approved for merge. The other validated functionality remains usable, but trainer acquisition must be corrected before another Release Candidate.
