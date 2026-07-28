# Kage Pilot Dojo — Adaptive Training

**Date:** 2026-07-28  
**Status:** future architecture; not implemented in the validated engine  
**Dependency:** first stabilize and prepare the canonical `kage_pilot_dojo.py` / v0.3i loop for merge

## Goal

Add a learning layer that improves Dojo training across many real rounds without allowing learning to weaken already validated safety rules.

The goal is not simply to win each fight in the shortest possible time. The correct objective is to maximize the number of complete, stable and safe rounds per unit of time.

```text
complete round =
  find/click trainer
  + wait for and start fight
  + combat
  + recognize KO
  + return to trainer
  + recover HP/Chakra
  + reach READY
```

Example:

```text
Strategy A: 70 s combat + 20 s recovery = 90 s cycle
Strategy B: 40 s combat + 65 s recovery = 105 s cycle
```

Even though strategy B wins the fight faster, it is worse for continuous training.

## Recommended objective function

Primary metric:

```text
completed_rounds_per_hour
```

Equivalent per-round optimization target:

```text
total_cycle_seconds =
  request_seconds
  + spawn_wait_seconds
  + combat_seconds
  + return_seconds
  + recovery_seconds
```

The optimizer should minimize the median and p90 of `total_cycle_seconds`, not only `combat_seconds`.

Conceptual score:

```text
reward =
  - total_cycle_seconds
  - safety_penalties
  - failure_penalties
  - instability_penalties
```

Strong penalties:

- combat timeout;
- failure to recognize `has been Knocked-Out`;
- foreground loss;
- persistent key leakage after shutdown;
- second trainer click;
- `V` or `Y` used during combat;
- failure to disable `V` or `Y`;
- failure to reach `READY`;
- F12 required;
- dialog error;
- repeated resynchronizations in the same round.

## Per-round telemetry

Each round should create an immutable record, preferably JSONL, containing:

```text
round_id
started_at
completed_at
result
opponent_name (when available)
request_seconds
spawn_wait_seconds
combat_seconds
return_seconds
recovery_seconds
total_cycle_seconds
start_hp / end_combat_hp / ready_hp
start_chakra / end_combat_chakra / ready_chakra
h_attempts / h_confirmed_fires
directional_pulses
target_lost_seconds
engaged_search_seconds
motion_burst_hold_seconds
map_save_resync_count
obstacle_detour_count
y_fast_used
victory_chat_seen
ready_reached
foreground_losses
emergency_stop
policy_id
parameter_snapshot
```

Local models, adaptive history and results should remain outside Git, for example:

```text
data/kage_pilot/adaptive/
```

Only schemas, code, synthetic examples and documentation should be versioned.

## What may be learned first

The first version should not generate arbitrary new actions. It should select among small, safe variations of existing parameters.

Candidate parameters:

- `h_stable_seconds`;
- `h_cooldown_seconds`;
- `h_min_score`;
- `face_refresh_seconds`;
- `move_confirm_frames`;
- `max_no_progress_seconds`;
- conservative reacquisition intervals after resynchronization;
- H-use thresholds within approved ranges.

Example policies:

```text
policy_conservative:
  less frequent H, stronger confirmation

policy_balanced:
  current validated parameters

policy_aggressive_safe:
  slightly more frequent H without changing target and safety gates
```

## What must never be learned automatically

The following invariants remain fixed and outside the optimization space:

- `has been Knocked-Out` as combat-end authority;
- immediate release of all keys after KO;
- `R` as the only normally held combat key;
- arrows and `H` as short pulses;
- `V` forbidden during combat;
- `Y` forbidden during combat;
- `V` only after visual trainer confirmation;
- exactly one trainer click;
- direct `OK` button activation;
- minimum recovery of HP >= 90% and Chakra >= 50%;
- F12 emergency stop;
- fail-closed behavior on focus, dialog or chat failures;
- MotionBurstGuard, water/particle protection and no blind pursuit.

## Recommended learning strategy

### Stage 1 — Passive observation

Run the validated engine without changing its behavior and only record metrics for 20 to 50 rounds.

Goals:

- establish a real baseline;
- measure natural variation between opponents;
- identify where time is spent;
- determine whether H reduces total cycle time or only transfers time into recovery;
- measure frequency of `ENGAGED_SEARCH` and `MOTION_BURST_HOLD` states.

### Stage 2 — Offline analysis

Create reports per policy and per round:

- median and p90 total cycle;
- median combat time;
- median recovery time;
- success rate;
- safety failure count;
- marginal efficiency of each H use;
- time spent waiting without a target;
- resynchronization impact.

No automatic changes are applied in this stage.

### Stage 3 — Champion/Challenger in shadow mode

The current policy is the `champion`.

A candidate policy (`challenger`) analyzes every frame and records what it would have done without sending commands. Then compare:

- divergent decisions;
- additional H opportunities;
- estimated risk;
- turning/movement moments;
- likely cycle impact.

Only policies approved in shadow mode may receive real authority.

### Stage 4 — Controlled contextual bandit

For the first online learning stage, use a contextual bandit across a few pre-approved policies, not unrestricted reinforcement learning.

Flow:

```text
select safe policy_id
→ execute one complete round
→ measure reward and failures
→ update statistics
→ keep champion or test challenger
```

Each candidate must receive a minimum number of rounds before comparison. Promotion must require:

- statistically consistent median cycle improvement;
- no worse p90;
- no lower success rate;
- zero new safety violations;
- no excessive recovery increase;
- no key leakage.

### Stage 5 — Promotion and rollback

A policy becomes `champion` only after conservative automatic approval and human review.

Every policy needs:

```text
policy_id
created_at
parent_policy_id
parameter_snapshot
sample_count
median_cycle_seconds
p90_cycle_seconds
success_rate
safety_failure_count
status = candidate | champion | rejected | rolled_back
```

Any severe failure triggers immediate rollback to the last validated champion.

## Why not use unrestricted reinforcement learning now

The current system already includes a temporal imitation model (`TemporalCombatModel`) that learns navigation and skill actions from victorious examples. That model may be useful later as a reference and in shadow mode, but it does not directly optimize total round time or explicitly account for recovery and safety.

Unrestricted online RL would create unnecessary risks:

- physical exploration of bad actions in the game;
- incorrect toggle usage;
- difficulty separating real improvement from opponent variation;
- silent regressions in focus, chat and particle protection;
- too few samples per configuration.

The recommended progression is therefore:

```text
telemetry
→ offline analysis
→ shadow mode
→ contextual bandit among safe policies
→ only then evaluate deeper policy learning
```

## Optimizer context

To avoid comparing incomparable rounds, the selector may consider:

- HP and Chakra at fight start;
- initial enemy relative position;
- time until first validated target;
- particle/motion intensity;
- presence of map-save resync;
- opponent/name when available;
- policy used in the previous round;
- recent success and recovery history.

Context never authorizes breaking safety invariants.

## Future integration with `DojoTrainingService`

The adaptive layer should remain behind the public API and outside the UI.

Possible future contract:

```python
config = DojoTrainingConfig(rounds=0, adaptive=True)
service.start(config)
status = service.snapshot()
```

Possible additional status fields:

```text
active_policy_id
baseline_cycle_seconds
rolling_cycle_seconds
completed_rounds
learning_mode = off | observe | shadow | adaptive
```

The Game-tab `Dojo` toggle only starts/stops the service. A separate explicit control should enable adaptive learning; it must not be silently enabled.

## Gate before implementation

Before starting this layer:

- [ ] finish polishing the current release candidate;
- [ ] complete full test suite with `OK`;
- [ ] validate public command `kage_pilot_dojo.py`;
- [ ] execute at least 3 consecutive rounds;
- [ ] review and prepare the current PR for merge;
- [ ] merge only with Rafael's explicit approval;
- [ ] create a separate branch/PR for Adaptive Dojo Training;
- [ ] implement passive telemetry first;
- [ ] do not automatically change parameters during the first collected rounds.

## Decision

The adaptive layer is recommended, but it should be the next project built on top of the validated baseline, not part of final polishing for the current PR.

Its first product will not be an agent that changes itself. It will be a round recorder and analyzer capable of answering with evidence:

- which policy wins faster;
- which policy completes more rounds per hour;
- how much each extra H use saves in combat;
- how much that use costs in recovery;
- where the agent remains idle;
- which changes are safe candidates for controlled testing.
