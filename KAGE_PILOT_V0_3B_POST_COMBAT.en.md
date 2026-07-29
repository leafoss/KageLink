# Kage Pilot v0.3b — Calibrated post-combat (EN-US)

## Goal

Preserve the validated v0.3 combat loop while making post-victory recovery reliable on each computer.

## Victory

Victory remains authoritative through newly appended chat text:

```text
has been Knocked-Out
```

Once received, all combat keys are released immediately.

## Local leader calibration

The earlier supplied reference image did not score high enough against the real game capture. v0.3b teaches the sprite directly from the live game frame:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_leader_calibrate.py
```

In the calibration window, select the complete leader with a small floor margin and confirm with Enter/Space. The local file is saved at:

```text
data/kage_pilot/dojo_leader_template.png
```

That folder is ignored by Git.

## Camera memory

After a visual confirmation, the predicted leader position is shifted by camera `global_flow`. Memory may guide dead-man movement pulses while the sprite is hidden or temporarily off-screen.

Memory never authorizes meditation. `V` is only sent after the leader is visually reacquired and confirmed in an adjacent cell.

## Resources

Observed calibration on the Micro PC:

```text
Full HP     = 47 px
Full Chakra = 40 px
```

Meditation exits only after HP >= 90% and Chakra >= 50% across consecutive readings.

## Probe

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_postcombat_probe_v2.py --seconds 20
```

The probe is read-only and reports template source, score, bbox, HP and Chakra.

## Live v0.3b

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03b.py --seconds 90 --log kage_pilot_live_test_6.jsonl
```

v0.3b reuses the same validated combat loop and replaces only the post-combat detector/state machine.
