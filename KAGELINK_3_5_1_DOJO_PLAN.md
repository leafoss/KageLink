# KageLink 3.5.1 — Dojo reliability plan

## Scope

This branch changes only three areas:

1. per-session Dojo journal preserved on error or unclean shutdown;
2. canonical relative visual position, keyframes, relocalization and closed-loop return to the confirmed Trainer anchor;
3. responsive Desktop Dojo page with Summary, Settings, Images and Logs tabs.

## Non-goals

Do not change Trainer matching, thresholds, click behavior, dialog handling, combat, KO, recovery, abilities, F12, GAME interlock, APK protocol, Memory Reviewer, LeafOS, chat, connection or template storage.

## Technical sequence

1. Map current capture, motion, combat, return, ring-search, helper and Desktop UI paths.
2. Add an isolated UTF-8 session journal under `%LOCALAPPDATA%\KageLink\logs\dojo`.
3. Add an isolated visual-position subsystem with `KNOWN`, `UNCERTAIN` and `LOST` states.
4. Track camera/environment displacement and player screen displacement without treating sent keys as ground truth.
5. Add bounded keyframes and conservative relocalization with best/second-best margin checks.
6. Add a closed-loop return controller targeting the Trainer anchor `(0, 0)` and safe local/ring fallbacks.
7. Rebuild only the Dojo Desktop page using responsive grid containers, `after_idle` initialization and debounced resize handling.
8. Add PT-BR and EN-US strings and tests.
9. Align Setup, APK, PC Agent and release metadata to 3.5.1.
10. Generate Windows and Android artifacts from the same commit and keep the PR in Draft until physical stress testing.

**Never merge without Rafael's explicit authorization.**
