# AGENTS_RUNTIME.en.md — KageLink runtime, state, and organization

[Português](AGENTS_RUNTIME.md) · [Main Bible](AGENTS.en.md)

This chapter complements `AGENTS.en.md` and governs entrypoints, workers, subprocesses, persistence, Windows input, releases, and structural reorganizations.

## Packaged runtime

```text
KageLink.spec → unified_entry.py → unified_launcher.py → unified_app.py → app.py
KagePilotDojo.spec → kage_pilot_dojo.py → kage_pilot.py dojo
KagePilotRound.spec → isolated round helper
```

Before changing behavior, identify which file is the source, which is a compatibility wrapper, and which file is actually packaged.

## Canonical organization

- One public surface per subsystem.
- One canonical document per language and subsystem.
- Active names are versionless.
- History belongs to Git, tags, releases, and PRs.
- Versioned snapshots must not remain indefinitely in the active tree.
- Do not delete versioned modules still imported by specs, tests, or runtime; first create the canonical boundary, migrate references, run CI, and validate in the real game.

### Required consolidation stages

1. inventory files and references;
2. define the canonical name;
3. create a compatible wrapper;
4. migrate imports, specs, workflows, and tests;
5. run the full suite;
6. perform risk-proportional physical validation;
7. remove superseded snapshots;
8. update documentation and record rollback.

## Failures and retries

```text
SUCCESS
RETRYABLE_OPERATION_FAILURE
OPERATION_ABORTED
MODULE_UNAVAILABLE
PROCESS_FATAL
EMERGENCY_STOP
```

Retries repeat only the failed stage. Confirmed one-shot actions are not repeated while waiting for a response.

## Workers and subprocesses

Every thread, task, timer, watcher, and subprocess declares owner, start, stop, timeout, cancellation, cleanup, result, retry policy, and failure impact.

Subprocesses log commands without secrets, exit codes, timeouts, terminate/kill behavior, and cleanup. No child process may leave keys pressed.

## Window and input gate

Before input:

1. locate again;
2. validate HWND;
3. validate title/class;
4. validate PID/process;
5. validate root/child;
6. reject invisible/minimized targets;
7. confirm foreground when required;
8. revalidate before input;
9. validate coordinates;
10. execute and release in `finally`.

## Persistence

- canonical/evidence/identity/cursor: fail closed;
- reconstructible cache: quarantine and rebuild;
- configuration: backup and defaults with warning.

Never silently convert invalid session, identity, or cursor state into empty state.

## Release

`RELEASE_VERSION` is the version source. Workflows and builders must not hardcode the current number in paths.

CI must protect changes to entrypoints, specs, protocols, localization, persistence, `AGENTS*.md`, Kage Pilot, and Installer.

## Rollback

Every structural reorganization must be reversible through its commit/PR and must explicitly list old names retained as temporary compatibility layers.
