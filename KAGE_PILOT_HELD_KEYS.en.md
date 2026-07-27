# Kage Pilot — held keys

[Português](KAGE_PILOT_HELD_KEYS.md)

The Combat Learner must distinguish between a **held base key** and variable combat decisions.

Observed Dojo example: `R` stays pressed during much of the fight while `LEFT`, `RIGHT`, `H`, `V`, and other keys represent moment-to-moment decisions.

From this revision onward, training uses `actions.jsonl` by default: each contiguous action run counts as one example, whether it lasts 100 ms or several seconds. This prevents a held key from dominating the dataset merely because the Recorder captures roughly 10 frames per second.

To treat `R` as a base key:

```powershell
python kage_pilot.py train --model kage_pilot_model_r.json --exclude-key r --no-idle
```

To test the Pilot while keeping `R` pressed and applying learned actions on top:

```powershell
python kage_pilot.py pilot --model kage_pilot_model_r.json --hold-key r --confidence 0 --seconds 10
```

After the first test, progressively restore a higher confidence threshold.

Legacy frame-by-frame training remains available only for diagnostics:

```powershell
python kage_pilot.py train --model legacy.json --frame-samples
```
