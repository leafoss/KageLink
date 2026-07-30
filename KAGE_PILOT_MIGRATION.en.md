# Staged migration of Kage Pilot internal modules

[Português](KAGE_PILOT_MIGRATION.md) · [Kage Pilot](KAGE_PILOT.en.md) · [Runtime](AGENTS_RUNTIME.en.md)

**Status:** phase 1 — canonical boundaries and CI, without removing the validated engine  
**Base:** KageLink 3.5.0  
**Rule:** no complex `v03*` file may be removed before green CI and renewed real Windows/BYOND validation.

## Goal

Replace version-based names with responsibility-based names while preserving physically validated behavior and a clear Git rollback path.

## Canonical internal surface

```text
pc_agent.kage_pilot.dojo_training_service
pc_agent.kage_pilot.dojo_request
pc_agent.kage_pilot.dojo_templates
pc_agent.kage_pilot.trainer_search
pc_agent.kage_pilot.ko_identity
pc_agent.kage_pilot.combat_control
pc_agent.kage_pilot.post_combat

kage_pilot.py
kage_pilot_loop.py
kage_pilot_round.py
```

New imports, specs, services, and integrations must use these names.

## Effective migration in this phase

- `ko_identity.py` is now the canonical KO identity gate implementation;
- `ko_identity_v03k.py` remains only as a compatibility wrapper;
- `dojo_training_service.py` is now the canonical source/installed service implementation;
- `dojo_training_v03k.py` remains only as a compatibility wrapper;
- source-mode service execution uses `kage_pilot_loop.py`;
- source-mode loop execution uses `kage_pilot_round.py`;
- PyInstaller specs use both versionless entrypoints;
- the template API and new tests use canonical boundaries;
- CI includes a gate that rejects versioned references in public consumers.

## Compatibility still preserved

The following chain still provides the physically validated engine:

```text
kage_pilot_loop_v03g.py
kage_pilot_loop_v03j.py
kage_pilot_live_v03.py
kage_pilot_live_v03e_round.py
kage_pilot_live_v03g_round.py
kage_pilot_live_v03h_round.py
kage_pilot_live_v03i_round.py
kage_pilot_live_v03j_round.py
kage_pilot_live_v03k_round.py
pc_agent/kage_pilot/*_v03*.py
```

These files are not new public surfaces. They are temporary compatibility providers and must not receive new parallel version snapshots.

## Conditions for the next extraction

A file group may be converted into a canonical implementation and removed only when:

1. all official consumers use the responsibility-based name;
2. an equivalent canonical test exists for every protected behavior;
3. the complete Python suite is green;
4. all three executables build and pass smoke tests;
5. Setup and APK build;
6. the corresponding physical validation has been executed;
7. results and logs are recorded in this document or the PR;
8. an identifiable rollback exists.

## Mandatory physical validation matrix

Record for each run:

```text
tested commit
Setup version
Windows
BYOND/game version
template mode: 32 or 64
configuration
log path
result
anomalies
```

### A. Startup and packaging

- install/update without system Python;
- open `KageLink.exe`;
- start `KagePilotDojo.exe` through UI/API;
- confirm `KagePilotRound.exe` starts without an orphan console;
- stop and confirm no orphan child processes remain.

### B. Templates

- test the 32×32 template alone;
- test the 64×64 template alone;
- test both configured simultaneously;
- confirm update/reinstall preserves both;
- confirm fail-closed behavior without a valid template.

### C. Trainer and dialog

- exactly one Trainer click per round;
- dialog found on check 1;
- dialog found on check 2;
- dialog found on check 3;
- dialog found on check 4;
- dialog never found: round ends without combat and the next round starts;
- no retry moves, searches for, or clicks the Trainer again;
- invalid HWND/PID blocks OK input.

### D. Combat

- approach and facing with a visible target;
- `R` held while arrows/`H` remain pulses;
- particle burst blocks movement and `H`;
- one facing correction during burst only when authorized;
- map-save resync releases inputs and reacquires perception;
- focus/window loss blocks input.

### E. KO and identity

- current different-opponent KO is accepted;
- previous-opponent repeated KO is rejected;
- rejection releases inputs, invalidates the target, and keeps combat active;
- KO without two current visual observations does not end the round;
- complete names with rank, comma, and spaces are preserved.

### F. Return and recovery

- visual return to the Trainer;
- self-occlusion uses at most one perpendicular pulse;
- memory alone never authorizes `V`;
- recovery requires HP ≥ 90% and Chakra ≥ 50%;
- `Y` toggles only under protected conditions;
- cleanup turns `Y` off when required.

### G. Stop and isolation

- F12 during Trainer search;
- F12 during every dialog wait;
- F12 during combat;
- F12 during return/recovery;
- no key remains pressed;
- manual GAME remains blocked during training;
- chat, history, STATS, and LeafOS remain available.

## Decision after validation

- **Passed:** extract the next implementation group into the canonical module and convert the old file into a thin wrapper.
- **Failed:** retain the old provider, fix on a branch, and repeat affected scenarios plus the complete regression.
- **Not tested:** removal is forbidden.

## Suggested next phases

1. service and KO identity — already migrated;
2. templates and Trainer search;
3. request/dialog gate;
4. combat control and particle safety;
5. post-combat/return/recovery;
6. final round composition;
7. final loop composition;
8. remove wrappers with no consumers.
