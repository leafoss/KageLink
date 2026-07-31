# KageLink 3.5.1 — Dojo reliability plan

## Scope

This Draft branch changes six tightly bounded areas:

1. per-session Dojo journal preserved on error or unclean shutdown;
2. canonical relative visual position, keyframes, relocalization and closed-loop return to the confirmed Trainer anchor;
3. responsive Desktop Dojo page with Summary, Settings, Images and Logs tabs;
4. protected meditation entry/exit transitions that prevent a round from starting while `V` is still locked by the game;
5. an optional click-through visual debug overlay fed by read-only Dojo snapshots;
6. backend-backed Start-bound settings, including percentage opacity and a 40% Chakra recovery floor.

## Controlled recovery exception

Combat, KO and the general recovery implementation remain outside this PR's scope. The authorized recovery changes are the critical meditation transition fix and the corrected global readiness contract: HP must be at least 90% and Chakra must be at least 40%.

The 3.5.1 layer must:

- treat a sent `V` as an intention, never as proof that meditation changed state;
- enforce at least five seconds for both entry and exit transitions;
- use monotonic timestamps instead of a blocking sleep;
- centralize `V` ownership and reject duplicate/unowned requests;
- keep combat blocked in `ENTERING_MEDITATION`, `MEDITATING` and `EXITING_MEDITATION`;
- skip meditation when valid HP and Chakra readings already meet their configured targets;
- accept Chakra targets from 40% through 100%, with 40% as the default and minimum;
- fail closed after a recovery timeout and request a protected exit before aborting;
- resume the PR23 visual return only after meditation exit has completed.

## Settings contract

The Desktop must load current values from the backend without continuously overwriting user edits. Numeric and selection edits remain local until **Start** is clicked. Start sends the complete visible configuration, the backend persists the debug values, and the runtime starts with those exact settings.

Opacity is displayed as an integer percentage from `10` to `100` and converted at the API boundary:

```text
85 → 0.85
10 → 0.10
```

Periodic status updates may refresh only fields that the user has not edited. A successful Start clears the dirty state and synchronizes the returned backend values.

## Visual debug contract

The overlay is optional and defaults to disabled. It:

- follows the exact game render-client rectangle;
- is borderless, topmost, no-activate and click-through;
- shows current state, HP, Chakra, `V` cooldown, position state, confidence, Trainer box and combat gate;
- receives immutable snapshots and never performs detection or control decisions;
- is excluded from screen capture with `WDA_EXCLUDEFROMCAPTURE` where Windows supports it;
- remains outside the window-specific `PrintWindow` capture path;
- can be toggled by the Desktop setting at Start or by F10 while the round process is active;
- supports PT-BR and EN-US controls in the responsive Dojo page.

The initial `processed` level currently exposes the complete detection/decision layer over the live game view. A separate thumbnail of intermediate OpenCV buffers remains a physical-test follow-up; the overlay must not duplicate image processing merely to render debug chrome.

## Non-goals

Do not change Trainer matching, templates, thresholds, click behavior, dialog handling, combat targeting, KO identity, abilities, F12, GAME interlock, APK protocol, Memory Reviewer, LeafOS, chat, connection or template storage.

Do not replace PR23 files with versions from `main`, create a parallel state machine, or introduce a second persistent journal.

## Technical sequence

1. Map current capture, motion, combat, return, ring-search, helper and Desktop UI paths.
2. Add an isolated UTF-8 session journal under `%LOCALAPPDATA%\KageLink\logs\dojo`.
3. Add an isolated visual-position subsystem with `KNOWN`, `UNCERTAIN` and `LOST` states.
4. Track camera/environment displacement and player screen displacement without treating sent keys as ground truth.
5. Add bounded keyframes and conservative relocalization with best/second-best margin checks.
6. Add a closed-loop return controller targeting the Trainer anchor `(0, 0)` and safe local/ring fallbacks.
7. Wrap the current PR23 recovery engine with a non-blocking meditation transition guard.
8. Publish unified debug snapshots without duplicating OpenCV work.
9. Add a Windows click-through overlay and a JSON control boundary shared with the Desktop UI.
10. Rebuild only the Dojo Desktop page using responsive grid containers, `after_idle` initialization and debounced resize handling.
11. Preserve local edits with dirty-field tracking and apply all visible values on Start.
12. Align the API, config, helper and runtime to the 40% Chakra floor and 10–100% opacity input.
13. Add PT-BR and EN-US strings and regression tests.
14. Align Setup, APK, PC Agent and release metadata to 3.5.1.
15. Generate Windows and Android artifacts from the same commit and keep the PR in Draft until physical stress testing.

## Required validation

Automated coverage must include:

- a second `V` cannot be sent during the protected entry interval;
- combat remains blocked until the protected exit interval completes;
- configured delays cannot fall below five seconds;
- timeout recovery never releases the next round;
- Chakra `40` is accepted, values below `40` are rejected, and the helper receives `0.4`;
- opacity `10` is accepted and reaches the runtime as `0.10`;
- backend status fills untouched fields but never overwrites locally edited fields;
- Start sends and stores the complete visible configuration;
- the authenticated debug route and start-route bridge are installed;
- debug settings persist, normalize unsafe values and fail closed on malformed input;
- the existing journal, visual-position, relocalization, closed-loop return and responsive UI tests remain green.

Physical Windows/BYOND validation must confirm:

- HP at or above 90% and Chakra at or above 40% can proceed without unnecessary meditation;
- Chakra below 40% triggers recovery;
- changing opacity from 85 to 10 and clicking Start runs the overlay at 10%;
- edited values remain visible before Start despite status polling;
- the overlay aligns after move, resize, maximize and DPI scaling;
- mouse and keyboard input pass through the overlay;
- the captured OpenCV frame never contains overlay graphics;
- F12 still releases all keys and stops safely.

**Never merge without Rafael's explicit authorization.**
