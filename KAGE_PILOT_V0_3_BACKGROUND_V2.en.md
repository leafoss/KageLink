# Kage Pilot v0.3 — Background Dynamic v2

## Why the first water filter failed

The first dynamic-background filter depended heavily on two conditions at the same time:

- several nearby candidates;
- high visual similarity between the current candidate and the region memory.

Animated water in Shinobi Story Online continuously changes contour shape and position. The same water band could therefore create dozens of `ENTITY #NNN` tracks even though it was clearly scenery.

## New strategy: temporal occupancy

v2 learns where dense motion repeatedly returns:

```text
motion detected
    ↓
several nearby candidates
    ↓
bounding boxes occupy the same arena cells
    ↓
activity persists across multiple frames
    ↓
BACKGROUND_DYNAMIC
```

Appearance is still used, but as supporting evidence. Regions with strong repetitive occupancy can be suppressed even when the animation changes visually.

## Protecting real entities

The filter must not erase an opponent just because it crosses animated water.

Established tracks are protected when they show combat evidence, including:

- proximity to the player;
- movement toward the player;
- hostility memory;
- `OCCLUDED` contact state.

## Retroactive cleanup

The first version filtered new candidates, but a false entity created before water had been learned could remain alive for the active TTL and even compete for `TARGET LOCK`.

v2 also reviews active tracks. A track far from the player, without hostile behavior, inside a strongly dynamic region and with low-coherence motion can be removed as animated background.

This allows the `entities` count to fall after the region is learned instead of only preventing new false positives.

## PLAYER recalibration

Click calibration still clears entity identity and target lock, but it no longer clears already learned environmental memory.

Repeated adjustment clicks on Leafos therefore do not make the Observer forget the water and restart learning from zero.

## Expected validation

When Leafos approaches animated water:

1. some candidates may initially appear;
2. `dynamic bg cells` should grow;
3. `dynamic bg suppressed` should start increasing;
4. the `entities` count should drop significantly;
5. water should not acquire or retain `TARGET LOCK`;
6. a real opponent near the player should remain trackable despite the animation.

This layer remains **observation only** and sends no keyboard input to the game.
