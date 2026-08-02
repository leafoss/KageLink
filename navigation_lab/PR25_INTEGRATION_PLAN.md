# PR 25 integration plan

PR 25 must integrate the approved Navigation Lab through narrow adapters. It must not move navigation domain logic into KageLink.

## Stable candidate interfaces

- destination command source;
- frame source;
- input adapter;
- telemetry sink;
- profile and storage resolver.

## Expected integration

```text
KageLink command or UI
        ↓
Navigation destination adapter
        ↓
Approved PR 24 navigation service
        ↓
KageLink frame and input adapters
        ↓
Existing GAME safety boundary
```

## Prohibited integration

- importing Dojo behavior into navigation;
- duplicating A*, world graph or map persistence inside KageLink;
- bypassing focus and input-release safety;
- using Android or WebSocket state as the navigation database;
- silently enabling autonomous control.

## Merge order

1. Merge PR 23 after its independent physical gate.
2. Update the PR 24 branch from the resulting `main` and rerun all tests.
3. Complete and approve PR 24 physical navigation gate.
4. Merge PR 24.
5. Create PR 25 from the new `main`.
