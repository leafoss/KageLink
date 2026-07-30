# AGENTS_RUNTIME.en.md — Runtime, state, and organization

[Português](AGENTS_RUNTIME.md) · [Bible](AGENTS.en.md) · [3.5 Addendum](AGENTS_3_5.en.md)

This chapter governs entrypoints, workers, subprocesses, persistence, Windows input, and structural reorganizations.

## Packaged runtime

```text
KageLink.spec → unified_entry.py → unified_launcher.py → unified_app.py → app.py
KagePilotDojo.spec → kage_pilot_dojo.py → kage_pilot.py dojo
KagePilotRound.spec → isolated round runtime
```

Before changing behavior, identify the source file, compatibility wrapper, and actual packaged entrypoint.

## Canonical organization

- one public surface per subsystem;
- one canonical document per language and subsystem;
- active names are versionless;
- history belongs to Git, tags, releases, and PRs;
- versioned snapshots must not remain indefinitely in the active tree.

Do not delete modules still imported by runtime, specs, workflows, or tests.

### Consolidation stages

1. inventory files and references;
2. define the canonical name;
3. create a compatible wrapper;
4. migrate imports, specs, workflows, and tests;
5. run the complete suite;
6. perform risk-proportional physical validation;
7. remove superseded snapshots;
8. update documentation and record rollback.

## Workers and subprocesses

Every thread, task, timer, watcher, and subprocess declares:

- owner;
- start/stop conditions;
- timeout;
- cancellation;
- cleanup;
- result;
- retry policy;
- failure impact.

`daemon=True` is not lifecycle management. Subprocesses log commands without secrets, exit codes, and terminate/kill policy. No child may leave inputs active.

## Window and input gate

Before input:

1. locate again;
2. validate HWND;
3. validate title/class;
4. validate PID/process;
5. validate root/child;
6. reject invisible/minimized targets;
7. confirm foreground when required;
8. revalidate immediately before input;
9. validate coordinates;
10. execute and release in `finally`.

Never trust stale HWNDs or coordinates blindly.

## Persistence

- canonical/evidence/identity/cursor: fail closed;
- reconstructible cache: quarantine and rebuild;
- configuration: backup and defaults with warning.

Invalid session, identity, or cursor state must never silently become empty state.

## Release

`RELEASE_VERSION` is the version source. Workflows and builders must not hardcode the current version in paths.

CI must protect entrypoints, specs, protocols, localization, persistence, `AGENTS*.md`, Kage Pilot, and Installer.

## Rollback

Every reorganization must be reversible through its commit/PR and list old names retained temporarily for compatibility.
