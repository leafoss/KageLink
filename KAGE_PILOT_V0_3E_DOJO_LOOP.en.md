# Kage Pilot v0.3e — Full Dojo Loop

Date: 2026-07-28

## Goal

Close a bounded and observable cycle:

```text
READY beside the trainer
→ click the trainer once
→ locate the game-process #32770 dialog and ListBox
→ keep “Taijutsu Dojo Spar” (index 0) selected
→ wait 10 seconds from the click
→ Enter
→ wait 5 seconds
→ validated v0.3 combat
→ chat-authoritative victory: “has been Knocked-Out”
→ return/search for trainer
→ V to enter meditation
→ HP >= 90% and Chakra >= 50%
→ V to leave meditation
→ READY
→ next round, when configured
```

## Safety

- F12 interrupts waits, combat and post-combat.
- R and H are never used during return, search, meditation or dialog handling.
- V remains a toggle: one tap enters meditation, a second tap exits.
- The dialog is identified by game process, top-level class `#32770`, and a child `ListBox`; numeric HWND values are never persisted.
- The trainer click requires a current visual confirmation and grid distance `d <= 1`.
- Trainer memory may guide movement but can never authorize V or a click.
- The default loop runs only one round.

## Obstacles

After a directional pulse, the next frame measures:

- global camera-motion magnitude;
- mean captured-arena difference.

Two consecutive no-motion readings temporarily block that direction. Search abandons the current ring segment and tests the next direction. The block expires so the direction may be reassessed later.

A partial trainer similarity between `0.80` and the normal threshold causes only a short confirmation pause. It cannot authorize navigation, clicking or meditation, and it cannot freeze search indefinitely.

## Executables

### Isolated obstacle test

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_postcombat_live_test_v03e.py --seconds 90 --search-timeout 90
```

### Isolated request test

This starts a real fight and exits after the spawn wait:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_dojo_request_test_v03e.py
```

### One complete round

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_loop_v03e.py --rounds 1
```

### Three complete rounds

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_loop_v03e.py --rounds 3
```

### Until F12

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_loop_v03e.py --rounds 0
```

The until-F12 mode should only be used after several successful bounded rounds.

## Main files

- `pc_agent/kage_pilot/post_combat_v03e.py`
- `pc_agent/kage_pilot/dojo_fight_v03e.py`
- `kage_pilot_postcombat_live_test_v03e.py`
- `kage_pilot_dojo_request_test_v03e.py`
- `kage_pilot_live_v03e_round.py`
- `kage_pilot_loop_v03e.py`
- `tests/test_kage_pilot_v03e_loop.py`
