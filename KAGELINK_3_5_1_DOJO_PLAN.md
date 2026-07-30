# KageLink 3.5.1 — Dojo reliability plan

## Scope

This Draft branch changes five tightly bounded areas:

1. per-session Dojo journal preserved on error or unclean shutdown;
2. canonical relative visual position, keyframes, relocalization and closed-loop return to the confirmed Trainer anchor;
3. responsive Desktop Dojo page with Summary, Settings, Images and Logs tabs;
4. protected meditation entry/exit transitions that prevent a round from starting while `V` is still locked by the game;
5. an optional click-through visual debug overlay fed by read-only Dojo snapshots.

## Controlled recovery exception

Combat, KO and the general recovery policy remain outside this PR's scope. The only recovery change authorized here is the critical meditation transition fix required to prevent the next round from starting while the character is still meditating.

The 3.5.1 layer must:

- treat a sent `V` as an intention, never as proof that meditation changed state;
- enforce at least five seconds for both entry and exit transitions;
- use monotonic timestamps instead of a blocking sleep;
- centralize `V` ownership and reject duplicate/unowned requests;
- keep combat blocked in `ENTERING_MEDITATION`, `MEDITATING` and `EXITING_MEDITATION`;
- skip meditation when valid HP and Chakra readings already meet their configured targets;
- fail closed after a recovery timeout and request a protected exit before aborting;
- resume the PR23 visual return only after meditation exit has completed.

## Visual debug contract

The overlay is optional and defaults to disabled. It:

- follows the exact game render-client rectangle;
- is borderless, topmost, no-activate and click-through;
- shows current state, HP, Chakra, `V` cooldown, position state, confidence, Trainer box and combat gate;
- receives immutable snapshots and never performs detection or control decisions;
- is excluded from screen capture with `WDA_EXCLUDEFROMCAPTURE` where Windows supports it;
- remains outside the window-specific `PrintWindow` capture path;
- can be toggled by the Desktop setting or F10 while the round process is active;
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
9. Add a Windows click-through overlay and a live JSON control boundary shared with the Desktop UI.
10. Rebuild only the Dojo Desktop page using responsive grid containers, `after_idle` initialization and debounced resize handling.
11. Add PT-BR and EN-US strings and regression tests.
12. Align Setup, APK, PC Agent and release metadata to 3.5.1.
13. Generate Windows and Android artifacts from the same commit and keep the PR in Draft until physical stress testing.

## Required validation

Automated coverage must include:

- a second `V` cannot be sent during the protected entry interval;
- combat remains blocked until the protected exit interval completes;
- configured delays cannot fall below five seconds;
- timeout recovery never releases the next round;
- the authenticated debug route and start-route bridge are installed;
- debug settings persist, normalize unsafe values and fail closed on malformed input;
- the existing journal, visual-position, relocalization, closed-loop return and responsive UI tests remain green.

Physical Windows/BYOND validation must confirm:

- the exact HP > 90% / Chakra = 50% regression no longer starts combat in meditation;
- the overlay aligns after move, resize, maximize and DPI scaling;
- mouse and keyboard input pass through the overlay;
- the captured OpenCV frame never contains overlay graphics;
- F12 still releases all keys and stops safely.

**Never merge without Rafael's explicit authorization.**
