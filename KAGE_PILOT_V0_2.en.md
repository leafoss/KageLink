# Kage Pilot v0.2

[Português](KAGE_PILOT_V0_2.md)

**Kage Pilot v0.2** replaces the old "one image → one key" concept with a temporal combat model tailored to the Shinobi Story Online Dojo.

## Combat model

```text
R held = base combat state / automatic melee attack

previous frame + current frame
              ↓
       temporal context
              ↓
     ┌────────┴────────┐
     ↓                 ↓
 Navigation          Jutsus
UP/DOWN/                H /
LEFT/RIGHT          configurable
     ↓                 ↓
     └────────┬────────┘
              ↓
            + R

victory
   ↓
V = meditation / post-combat
```

Navigation and jutsus are learned independently. `R` remains the combat base state. `V` is **not a combat skill**: by default it marks the beginning of the post-fight tail and is excluded from combat training.

## Changes from v0.1

- uses frame pairs to capture visual change and motion;
- `R` is a permanent base key by default instead of a learned action;
- `UP`, `DOWN`, `LEFT`, and `RIGHT` form a dedicated navigation policy;
- `H` is the initial default combat skill; more skills can be configured;
- `V` is post-combat/meditation by default;
- when `V` appears in a demonstration, training discards `V` and the remaining tail from combat learning;
- each class is compared against real action-run examples rather than only one averaged class image;
- a large number of `idle` examples does not vote against `LEFT/RIGHT`;
- after a jutsu fires, the skill policy must return to `idle` before the same state can fire again;
- jutsus also retain a cooldown;
- `--debug` shows decisions, confidence, rearm state, and applied keys;
- configurable startup delay reduces focus races with PowerShell;
- the controller explicitly focuses `Shinobi Story Online` before control starts;
- temporal memory resets at the start of each Dojo fight;
- legacy v0.1 commands remain available for comparison.

## Existing data

Sessions recorded with v0.1 remain valid. v0.2 uses the same structure:

```text
sessions/<fight>/
├── manifest.json
├── samples.jsonl
├── actions.jsonl
└── frames/
```

v0.2 training consumes the `actions.jsonl` runs, so a key held for several seconds does not receive dozens of votes simply because of Recorder FPS.

## Train v0.2

From `KageLink Installer/pc_agent`:

```powershell
python kage_pilot.py train-v2 --model kage_pilot_v02.json
```

Current defaults:

```text
base key: R
combat skills: H
post-combat key: V
history: 2 frames
victory sessions only
```

To add another combat skill:

```powershell
python kage_pilot.py train-v2 --model kage_pilot_v02.json --skill-key h --skill-key g
```

To change the post-combat key:

```powershell
python kage_pilot.py train-v2 --model kage_pilot_v02.json --post-combat-key v
```

## Recommended first test

Enter a fight manually and run:

```powershell
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --seconds 15 --debug
```

The command waits 3 seconds before taking control. Debug output looks like:

```text
V0.2 nav=right:0.143 skill=idle:0.091 fire=- armed=yes keys=r+right
V0.2 nav=idle:0.112 skill=h:0.084 fire=h armed=no keys=h+r
```

The initial goal is not to win. First confirm that:

1. `R` stays active;
2. movement happens when needed;
3. the character stops moving when navigation predicts `idle`;
4. `V` is never used during combat;
5. `H` is not repeated continuously;
6. decisions change when relative positioning changes.

## Useful tuning

```powershell
# more conservative jutsu use
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --skill-confidence 0.05 --seconds 15 --debug

# longer jutsu cooldown
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --skill-cooldown 2.0 --seconds 15 --debug

# no startup delay
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --startup-delay 0 --seconds 15 --debug
```

## Dojo Manager v0.2

After the Dojo templates and sequences are calibrated:

```powershell
python kage_pilot.py dojo-v2 --model kage_pilot_v02.json --config dojo_config.json --cycles 10 --debug
```

The Dojo Manager remains deterministic. AI controls combat only. `V` meditation belongs to the post-result sequence, not to the jutsu policy.

## Current boundary

v0.2 has temporal visual memory and now uses real per-class examples, but it still does not include an explicit supervised detector drawing boxes around `Leafos` and the enemy. This stage checks whether these corrections are enough to learn pursuit/repositioning in the controlled Dojo. If navigation still remains `idle` during clear separation, the next step is explicit player/enemy visual calibration on top of this architecture without discarding the current dataset.
