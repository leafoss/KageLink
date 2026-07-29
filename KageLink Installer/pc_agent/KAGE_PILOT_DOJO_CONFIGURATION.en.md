# Kage Pilot Dojo — Configuration

**Status:** v0.3j release-candidate public contract  
**Canonical file:** `config/kage_pilot_dojo.json`

## Purpose

Keep the basic training settings in one place that is easy to edit, review and later expose in KageLink's Game tab.

The JSON file controls:

- number of rounds;
- waits between stages;
- search, combat and recovery timeouts;
- HP and Chakra percentages required for `READY`;
- guarded `H` usage;
- trainer visual threshold;
- log directory.

Safety logic is not configurable through this file.

## Default file

```json
{
  "schema_version": 1,
  "rounds": 1,
  "timing": {
    "after_trainer_click_seconds": 5.0,
    "dialog_find_timeout_seconds": 6.0,
    "after_dialog_ok_seconds": 5.0,
    "combat_timeout_seconds": 120.0,
    "post_combat_timeout_seconds": 240.0,
    "trainer_search_timeout_seconds": 90.0,
    "round_startup_delay_seconds": 1.0,
    "chat_poll_seconds": 0.15
  },
  "recovery": {
    "hp_percent": 90.0,
    "chakra_percent": 50.0
  },
  "combat": {
    "h_enabled": true
  },
  "detection": {
    "leader_threshold": 0.88
  },
  "logging": {
    "directory": "kage_pilot_loop_logs"
  }
}
```

## Fields

### General control

| Field | Meaning |
|---|---|
| `rounds` | `1` runs one round; `0` repeats until disabled/F12. |

### Timing

| Field | Meaning |
|---|---|
| `after_trainer_click_seconds` | Wait between the single trainer click and dialog confirmation. |
| `dialog_find_timeout_seconds` | Maximum time to locate the dialog and real `OK` button. |
| `after_dialog_ok_seconds` | Wait after `OK` for the opponent to appear. |
| `combat_timeout_seconds` | Maximum combat-stage duration; KO may end it earlier. |
| `post_combat_timeout_seconds` | Limit for return, meditation and reaching `READY`. |
| `trainer_search_timeout_seconds` | Limit for locating the trainer before the fight. |
| `round_startup_delay_seconds` | Short wait after foregrounding the game before control starts. |
| `chat_poll_seconds` | Chat polling interval for KO detection. |

### Recovery

| Field | Allowed range | Default |
|---|---:|---:|
| `hp_percent` | `90` to `100` | `90` |
| `chakra_percent` | `50` to `100` | `50` |

The `90% HP` and `50% Chakra` floors are validated baseline safety invariants. Configuration may increase them but cannot lower them.

### Combat and detection

| Field | Meaning |
|---|---|
| `h_enabled` | `true` enables guarded `H`; `false` keeps base attack/facing only. It must be a real JSON boolean without quotes. |
| `leader_threshold` | Minimum trainer-template visual confidence. |

## Usage

Show the effective configuration without starting the game:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py --show-config
```

Run with the default file:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py
```

Use another file:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py `
  --config ".\config\my_dojo.json"
```

Temporarily override values without editing JSON:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo.py `
  --rounds 3 `
  --dialog-delay 4 `
  --spawn-delay 5 `
  --recovery-hp-percent 95 `
  --recovery-chakra-percent 60
```

Precedence:

```text
PowerShell argument
→ JSON file
→ DojoTrainingConfig internal default
```

## Fail-closed validation

The program does not start when it finds:

- invalid JSON;
- a section with the wrong shape;
- an unknown key;
- an unsupported schema version;
- `h_enabled` that is not a real `true` or `false`;
- HP below 90% or above 100%;
- Chakra below 50% or above 100%.

Configuration errors exit with code `2` and `DOJO_CONFIG_ERROR / ERRO_CONFIG_DOJO`.

## Rules that remain fixed

The JSON cannot change:

- `has been Knocked-Out` as combat-end authority;
- immediate release of every key after KO;
- exactly one trainer click;
- direct `OK` button activation;
- no `V` or `Y` during combat;
- `V` only after visual trainer confirmation;
- `R` as the only normally held key;
- arrows and `H` as pulses;
- `MAP_SAVE_RESYNC`, `H_SETTLE_HOLD` and other safety gates;
- F12 emergency stop.

## Future integration

The app must not parse the JSON and duplicate runtime logic. The Game tab should build/update a `DojoTrainingConfig` and call only `DojoTrainingService`.

Visible future UI text must use the PT-BR/EN-US internationalization system; JSON field names are stable technical identifiers.
