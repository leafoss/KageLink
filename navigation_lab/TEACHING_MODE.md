# Teaching Mode design gate

Teaching Mode is specified but intentionally not activated in the first simulator milestone.

## Planned flow

1. Find and validate the exact `Shinobi Story Online` window.
2. Capture only the configured client area.
3. User moves the character manually.
4. Navigation Lab estimates displacement and confidence.
5. Configurable keys create typed annotations.
6. Each annotation stores position, region, source, timestamp and evidence frame reference.
7. The operator confirms, edits or removes the annotation.
8. The map is saved atomically under the active profile.

## Default proposed keys

- F6: mark location;
- F7: mark entry or exit;
- F8: mark obstacle;
- F9: name region;
- F10: save demonstrated route;
- F11: mark destination;
- F12: pause or resume learning.

These values already exist in `config/defaults.json` and must remain configurable.

## Acceptance requirement

Teaching Mode may be enabled only after the debug window can show the original frame, processed frame, estimated pose, confidence, annotation type and exact persisted record for the same action.
