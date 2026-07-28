# Kage Pilot v0.3c — Dojo trainer return (EN-US)

## Validated problem

The v0.3b post-combat loop works when the trainer is visible or when visual memory already exists. If a test starts with the trainer off-screen and no memory, the system remains stationary in `SEEK_LEADER`.

## v0.3c strategy

The combat policy is unchanged. v0.3c adds only auxiliary perception and post-combat navigation.

### 1. Persistent anchor during combat

On every combat frame, the local trainer template is searched read-only. After the first visual confirmation, its position is retained through the fight and shifted by camera `global_flow`.

```text
last visually confirmed trainer position
+ per-frame global camera displacement
= current predicted position
```

Memory lasts up to 180 seconds in this revision.

### 2. Memory-guided return

After the authoritative `has been Knocked-Out` message, every combat key is released. When an anchor exists, Leafos returns through short pulses until the trainer becomes visible again.

Log state:

```text
RETURN_TO_LEADER
```

Memory may guide walking but can never authorize `V`.

### 3. Bounded search without an anchor

If the trainer was never seen by the current process, an expanding-square search starts:

```text
UP 1
RIGHT 1
DOWN 2
LEFT 2
UP 3
RIGHT 3
...
```

Each unit is composed of dead-man pulses. Arrow keys are never held. Search stops immediately when the visual template reappears and is bounded by both time and radius.

States:

- `SEARCH_WAIT`: short wait before searching;
- `SEARCH_LEADER`: one bounded-search pulse;
- `SEARCH_HOLD`: bound reached; no key is sent.

### 4. Meditation remains visually protected

Even when memory predicts `d <= 1`, the system waits for the trainer to reappear and requires two current visual confirmations before tapping `V`.

```text
visual confirmation + adjacency
→ tap V once
→ HP >= 90% and Chakra >= 50%
→ tap V once
→ READY
```

## Safety

- `R` and `H` are never used during return;
- arrows remain short pulses only;
- `F12` stops immediately;
- foreground loss stops control;
- the search is bounded and must not be tested outside the safe Dojo area.

## Isolated test

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_postcombat_live_test_v03c.py --seconds 60
```

## Full cycle

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_live_v03c.py --seconds 90 --log kage_pilot_live_test_7.jsonl
```
