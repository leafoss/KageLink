# Kage Pilot v0.2 — Spatial Experiment

This mode is an experimental perception revision for Kage Pilot v0.2. It does **not replace** the main temporal model yet.

## Why it exists

Real Dojo tests validated the keyboard control path and `R` started working correctly after reproducing the BYOND repeated-`KEYDOWN` behavior. However, the original visual model still classified almost every situation as `idle`, with confidence close to zero.

That prevented the Pilot from:

- correcting `LEFT/RIGHT` after knockback or separation from the opponent;
- recognizing situations where `H` should be used;
- separating visually similar combat states well enough.

## New representation

The spatial experiment uses:

- a crop of the main arena region;
- current-frame edges/high-frequency detail to emphasize sprites and shapes;
- amplified signed temporal difference;
- a coarse regional motion-energy grid;
- per-feature normalization before comparison;
- class-balanced comparison against real demonstration examples.

Combat semantics remain unchanged:

- `R`: base combat state, physically emitted with BYOND repeat behavior;
- `LEFT/RIGHT/UP/DOWN`: learned navigation;
- `H`: separately learned combat skill;
- `V`: post-combat meditation, excluded from combat learning.

## Commands

Train from the existing demonstrations:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_spatial.py train --model kage_pilot_v02_spatial.json
```

Run a real test:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_spatial.py pilot --model kage_pilot_v02_spatial.json --seconds 20 --debug
```

The goal of this stage is not automatic victory. The first success criterion is seeing real `nav=left/right` decisions after separation and eventually `skill=h`, instead of permanent `idle`.
