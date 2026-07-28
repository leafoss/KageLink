# Kage Pilot v0.3j — Safe Dojo dialog retry

**Date:** 2026-07-28  
**Status:** implementation and automated tests approved; physical validation pending  
**Scope:** trainer → dialog → `OK` button gate only

## Root cause

During round 3 of a ten-round run, the trainer was found and correctly received one click. The dialog was not found during the first observation window, and `DOJO_DIALOG_NOT_FOUND` propagated as a fatal `DojoFightRequestError`.

The orchestrator treated every request failure as a reason to execute `break`, ending the complete loop after two completed rounds.

```text
ROUND 3: TRAINER_CLICK_ONCE
ROUND 3: DOJO_REQUEST_FAILED: DOJO_DIALOG_NOT_FOUND
DOJO_LOOP_STOPPED completed=2
```

The failure was not in trainer detection, clicking, combat or chat. It came from:

1. only one opportunity to find the dialog after the trainer click;
2. no recoverable “round finished without combat” result;
3. globally fatal handling of `DOJO_DIALOG_NOT_FOUND`.

## Chosen source of truth

The correction was applied to the canonical release-candidate path:

```text
kage_pilot_dojo.py
→ DojoTrainingService
→ kage_pilot_loop_v03j.py
→ kage_pilot_loop_v03g.py
→ dojo_fight_v03i.py
```

Responsibilities:

- `dojo_fight_v03i.py`: one click, waits, dialog revalidation, `OK` click and recoverable result;
- `kage_pilot_loop_v03g.py`: round semantics, loop continuation and counters;
- `kage_pilot_loop_v03j.py`: enables the robust policy in the validated entry point;
- `kage_pilot_dojo.py` and `DojoTrainingService`: remain the public contract without duplicating the gate.

No second parallel retry implementation was introduced.

## Absolute one-click rule

Per round:

```text
trainer_clicks <= 1
```

After `TRAINER_CLICK_ONCE`, the code may not:

- search for the trainer again;
- move to reacquire the trainer;
- click the trainer sprite again;
- repeat the spar request;
- reuse trainer coordinates.

All retries operate only on the dialog that was already requested.

## New flow

With `--dialog-delay 5` and default `--dialog-retries 3`:

```text
SEARCH_TRAINER
→ VISUAL_CONFIRM
→ TRAINER_CLICK_ONCE
→ release_all

→ WAIT 5s
→ DIALOG CHECK 1/4

→ WAIT 5s
→ DIALOG CHECK 2/4

→ WAIT 5s
→ DIALOG CHECK 3/4

→ WAIT 5s
→ DIALOG CHECK 4/4
```

The calculation is always:

```text
1 initial check
+ 3 retries
= 4 total checks
```

Every check:

1. keeps all inputs released;
2. searches the game process windows again;
3. validates the `#32770` class;
4. validates the `ListBox`, minimum item count and visible/enabled `OK` control;
5. re-enumerates the dialog immediately before the click;
6. confirms that all HWNDs remain valid inside `click_first_option_ok`;
7. clicks only the current `OK` control.

No fixed coordinates, historical HWNDs or previous-attempt matches are used.

## States and results

### Success

```text
TRAINER_CLICK_ONCE
→ DOJO_DIALOG_WAIT/RETRY_WAIT
→ DOJO_DIALOG_CONFIRMED
→ DOJO_DIALOG_OK_CLICKED
→ DOJO_REQUEST_OK
→ WAITING_FOR_SPAWN
→ START COMBAT RUNTIME
```

`DOJO_REQUEST_OK` is emitted only after current dialog confirmation and a valid `OK` button click.

### Four checks without a dialog

```text
TRAINER_CLICK_ONCE
→ four waits/checks
→ ABORTED reason=DOJO_DIALOG_NOT_FOUND trainer_clicks=1 dialog_attempts=4
→ FINISHED_WITHOUT_COMBAT
→ next round
```

The round consumes its number. Under `--rounds 10`, a round-3 failure still processes rounds 1 through 10; no compensating round 11 is created.

### F12

During any wait:

```text
F12
→ interrupt wait
→ release_all
→ EMERGENCY_STOP
→ stop the complete program
```

## Final counters

The summary now separates:

```text
requested
processed
completed
finished_without_combat
failed
emergency_stopped
```

Example with one recoverable failure in round 3:

```text
DOJO_LOOP_FINISHED requested=10 processed=10 completed=9 finished_without_combat=1 failed=0 emergency_stopped=0
```

## Example — success on the fourth check

```text
ROUND 3: TRAINER_CLICK_ONCE score=0.939 d=1
ROUND 3: DOJO_DIALOG_WAIT attempt=1/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=1/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=2/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=2/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=3/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=3/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=4/4 delay=5.0
ROUND 3: DOJO_DIALOG_CONFIRMED attempt=4/4 hwnd=...
ROUND 3: DOJO_DIALOG_OK_CLICKED attempt=4/4 hwnd=...
ROUND 3: DOJO_REQUEST_OK trainer_clicks=1 dialog_attempts=4
ROUND 3: WAITING_FOR_SPAWN delay=5.0
ROUND 3: START COMBAT RUNTIME
```

## Example — round finished without combat

```text
ROUND 3: TRAINER_CLICK_ONCE score=0.939 d=1
ROUND 3: DOJO_DIALOG_WAIT attempt=1/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=1/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=2/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=2/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=3/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=3/4
ROUND 3: DOJO_DIALOG_RETRY_WAIT attempt=4/4 delay=5.0
ROUND 3: DOJO_DIALOG_NOT_FOUND attempt=4/4
ROUND 3: ABORTED reason=DOJO_DIALOG_NOT_FOUND trainer_clicks=1 dialog_attempts=4
ROUND 3: FINISHED_WITHOUT_COMBAT
ROUND 4: SEARCH AND REQUEST TAIJUTSU DOJO SPAR
```

## Changed files

```text
pc_agent/kage_pilot/dojo_fight_v03i.py
kage_pilot_loop_v03g.py
kage_pilot_loop_v03j.py
tests/test_kage_pilot_dojo_dialog_retry.py
.github/workflows/kage-pilot-v03.yml
```

## Added tests

1. dialog found after initial wait;
2. dialog found after one retry;
3. dialog found after two retries;
4. dialog found after three retries;
5. dialog never appears;
6. exactly one trainer click guarantee;
7. F12 during wait;
8. HWND disappears before the `OK` click;
9. round 3 fails in a ten-round run and processing continues through round 10.

## Automated result

Official Windows Server 2025 runner, Python 3.11:

```text
41 targeted tests: OK
164 Kage Pilot tests: OK
292 complete PC Agent tests: OK
compilation: OK
canonical configuration: OK
```

## Preserved scope

The correction did not change:

- visual trainer detection;
- enemy vision/tracking;
- combat or facing logic;
- `MotionBurstGuard`;
- guarded `H` usage;
- chat-authoritative KO;
- trainer return;
- meditation, HP, Chakra or `Y`;
- obstacle policy;
- combat runtime.

## Remaining gate

The correction still requires a new multi-round physical game validation. The PR remains a draft and no merge is authorized.
