# Kage Pilot v0.3 — Shadow Combat

Shadow Combat is the intermediate stage between perception and automatic control.

It reuses the Dojo-validated Entity Observer with a 32×32 px logical GRID, `BACKGROUND_DYNAMIC`, `CONTACT_MEMORY`, `OCCLUDED`, and reacquisition. No key is sent to Shinobi Story Online.

The layer converts a validated TARGET into a hypothetical decision:

```text
no TARGET       -> SEARCH / HOLD
distant TARGET  -> MOVE_LEFT/RIGHT/UP/DOWN
contact TARGET  -> FACE_* / R_ON
stable visually confirmed contact -> H_READY
```

`H_READY` is deliberately forbidden when the target only exists through `CONTACT_MEMORY`; `VISIBLE` or `OCCLUDED` evidence, temporal stability, and cooldown are required.

The goal is to compare the system's decisions with manual fighting before connecting any output to `GameInputController`.

## Run

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_shadow.py --telemetry-seconds 1
```

Optionally record every decision to JSONL:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_shadow.py --telemetry-seconds 1 --log kage_pilot_shadow_test.jsonl
```

This mode defaults to a 32×32 px GRID, matching the July 2026 Dojo visual validation.
