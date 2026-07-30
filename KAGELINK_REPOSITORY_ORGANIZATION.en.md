# KageLink 3.5 repository organization

[Português](KAGELINK_REPOSITORY_ORGANIZATION.md)

## Goal

Reduce competing surfaces without breaking the physically validated Kage Pilot engine.

## Canonical active surface

```text
AGENTS.md + AGENTS_3_5.md + specialized chapters
KAGE_PILOT.md / KAGE_PILOT.en.md
KageLink Installer/pc_agent/kage_pilot.py
KageLink Installer/pc_agent/kage_pilot_loop.py
KageLink Installer/pc_agent/kage_pilot_dojo.py  # installed-helper wrapper
```

## Preserved external compatibility

```text
KageLink.exe
KagePilotDojo.exe
KagePilotRound.exe
```

These names are KageLink 3.5.0 distribution contracts and must not be removed incidentally.

## Versioned internal debt

The validated engine still depends on families such as:

```text
kage_pilot_loop_v03*
kage_pilot_live_v03*
pc_agent/kage_pilot/*_v03*
tests/test_kage_pilot_v03*
.github/workflows/kage-pilot-v03.yml
```

These files are not new public surfaces. They form a historical compatibility chain that must be extracted into responsibility-based canonical names in a separate functional PR.

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
- identifiable PR rollback.

Until that gate passes, internal files remain compatibility layers rather than the architectural pattern for new work.
