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
UP/DOWN/            H / V /
LEFT/RIGHT          configurable
     ↓                 ↓
     └────────┬────────┘
              ↓
            + R
```

Navigation and jutsus are learned independently. This prevents a frequent jutsu from being confused with movement and allows `R` to stay held throughout combat.

## Changes from v0.1

- uses frame pairs to capture visual change and motion;
- `R` is a permanent base key by default instead of a learned action;
- `UP`, `DOWN`, `LEFT`, and `RIGHT` form a dedicated navigation policy;
- `H` and `V` are the initial default skills and can be changed;
- jutsus use a cooldown to prevent per-frame spam;
- `--debug` shows decisions, confidence, and applied keys;
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

Initial defaults:

```text
base key: R
skills: H, V
history: 2 frames
victory sessions only
```

To add another skill:

```powershell
python kage_pilot.py train-v2 --model kage_pilot_v02.json --skill-key h --skill-key v --skill-key g
```

## Recommended first test

Enter a fight manually and run:

```powershell
python kage_pilot.py pilot-v2 --model kage_pilot_v02.json --seconds 15 --debug
```

The command waits 3 seconds before taking control. Debug output looks like:

```text
V0.2 nav=right:0.143 skill=idle:0.091 fire=- keys=r+right
V0.2 nav=idle:0.112 skill=h:0.084 fire=h keys=h+r
```

The initial goal is not to win. First confirm that:

1. `R` stays active;
2. movement happens when needed;
3. the character stops moving when navigation predicts `idle`;
4. jutsus are not repeated continuously;
5. decisions change when relative positioning changes.

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

The Dojo Manager remains deterministic. AI controls combat only.

## Current boundary

v0.2 has temporal visual memory but does not yet include an explicit supervised detector that draws boxes around `Leafos` and the enemy. This stage tests whether temporal information from demonstrations is sufficient to learn pursuit and repositioning in the controlled Dojo environment. If it is not, the next step is explicit player/enemy visual calibration on top of this architecture without discarding the current dataset.
