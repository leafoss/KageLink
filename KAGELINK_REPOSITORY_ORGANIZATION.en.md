# KageLink 3.5 repository organization

[Português](KAGELINK_REPOSITORY_ORGANIZATION.md) · [Kage Pilot migration](KAGE_PILOT_MIGRATION.en.md)

## Goal

Reduce competing surfaces without breaking the physically validated Kage Pilot engine.

## Canonical active surface

```text
AGENTS.md + AGENTS_3_5.md + specialized chapters
KAGE_PILOT.md / KAGE_PILOT.en.md
KageLink Installer/pc_agent/kage_pilot.py
KageLink Installer/pc_agent/kage_pilot_loop.py
KageLink Installer/pc_agent/kage_pilot_round.py
KageLink Installer/pc_agent/kage_pilot_dojo.py  # installed-helper wrapper
.github/workflows/kage-pilot.yml
```

Canonical internal modules:

```text
pc_agent.kage_pilot.dojo_training_service
pc_agent.kage_pilot.dojo_request
pc_agent.kage_pilot.dojo_templates
pc_agent.kage_pilot.trainer_search
pc_agent.kage_pilot.ko_identity
pc_agent.kage_pilot.combat_control
pc_agent.kage_pilot.post_combat
```

## Preserved external compatibility

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

These names are KageLink 3.5.0 distribution contracts and must not be removed incidentally.

## Migration status

Phase 1 moves official consumers, specs, the service, API, and CI to versionless names. `ko_identity.py` and `dojo_training_service.py` are already canonical implementations; their versioned equivalents remain temporary wrappers.

The complex chain still depends on families such as:

```text
kage_pilot_loop_v03*
kage_pilot_live_v03*
pc_agent/kage_pilot/*_v03*
tests/test_kage_pilot_v03*
```

These files are not public surfaces. They temporarily provide the validated patch composition and must not receive new parallel snapshots.

## New-file policy

Do not create permanent implementations using:

```text
v03x
final/final2
new/new2
hotfix
fix_latest
copy/copy2
```

During a major update:

1. update the subsystem's canonical file;
2. update changelog/release/PR evidence;
3. add tests to the canonical suite;
4. do not create a complete duplicate merely to represent the version.

## Snapshot-removal gate

Physical removal requires:

- automated inventory of imports and references;
- responsibility-based canonical internal names;
- updated PyInstaller specs;
- updated workflows;
- migrated tests without losing scenarios;
- green complete Python suite;
- build/smoke of all three EXEs;
- green Setup and APK;
- real validation of single click, dialog, combat, KO, return, recovery, F12, and GAME interlock;
- evidence according to `KAGE_PILOT_MIGRATION.en.md`;
- identifiable PR rollback.

Until this gate passes, internal files remain compatibility providers rather than the architectural pattern. A wrapper may be deleted only when it has no consumers and its corresponding physical validation has been recorded.
