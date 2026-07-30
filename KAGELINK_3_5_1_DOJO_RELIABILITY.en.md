# KageLink 3.5.1 — Dojo Trainer Reliability

[Português](KAGELINK_3_5_1_DOJO_RELIABILITY.md)

## Scope

Version 3.5.1 changes only three areas:

1. a per-session journal preserved only on error or incomplete shutdown;
2. relative visual position, keyframes, relocalization and return to the confirmed Trainer point;
3. a responsive Desktop page with Summary, Settings, Images and Logs tabs.

Trainer detection, thresholds, click behavior, dialog, combat, KO, recovery, F12, GAME interlock, templates and Android communication retain their previous contracts.

## Journal

Location:

```text
%LOCALAPPDATA%\KageLink\logs\dojo
```

Flow:

```text
start → flushed .active journal
success → summary + .active deletion
error → dojo_error_*.txt
crash/power loss → dojo_incomplete_*.txt on next startup
```

The Logs tab shows only the latest diagnostic and actions to open the file or folder.

## Visual position

Observed motion is authoritative:

```text
world motion = player screen motion - environment screen motion
```

Sent commands are intent. A push, teleport or jutsu can update X/Y without a command. A blocked command does not update X/Y.

States:

```text
KNOWN       position is usable
UNCERTAIN   evidence is insufficient for a long return
LOST        continuity was lost; coordinates must not be invented
```

## Keyframes and relocalization

The engine keeps a bounded set of visual references associated with X/Y. When continuity is lost, the character stops, releases keys and tries to recognize the current region. Restoration requires a minimum score and margin over the second candidate.

A teleport with no shared scenery and no known keyframe remains `LOST`; the system does not fabricate a return vector.

## Closed-loop return

Origin `(0,0)` is set when the Trainer is visually confirmed. After combat:

```text
stop and stabilize
→ relocalize when needed
→ choose one distance-reducing step
→ measure real displacement
→ update position
→ replan
→ stationary scan near origin
→ short local search
→ existing ring search
```

Pushes during return trigger replanning. Loops have timeout, step limits and F12/Stop interruption.

## Desktop

Tabs:

- **Summary:** runtime, phase, progress, round, compact location, controls and recent actions;
- **Settings:** existing parameters only;
- **Images:** 64×64 and 32×32 with sharp persistent previews;
- **Logs:** latest error, time, summary and paths.

The layout uses responsive grid containers, immediate construction, `after_idle` and debounced resize handling. It never maximizes or minimizes the window as a workaround.

## Physical test

1. install Setup 3.5.1;
2. confirm correct restored and maximized startup layout;
3. confirm Settings remains last;
4. validate 32×32 and 64×64 templates;
5. complete a session without a permanent error log;
6. trigger a controlled error and open the `.txt` through Logs;
7. observe X/Y while walking;
8. observe external displacement from push/jutsu;
9. test loss and relocalization in a mapped region;
10. test return while compensating another displacement;
11. validate local search and ring fallback;
12. validate F12, Stop and GAME interlock;
13. validate the APK against the same build.

The PR remains Draft and must not be merged without Rafael's explicit authorization.
