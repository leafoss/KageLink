# PR27 Sprite References

Optional visual references for the PR27 tracker.

Place transparent or tightly cropped PNG files in:

```text
player/
enemy/
npc/
unknown/
```

The filename becomes the `sprite_id`. References are compared only after a fragment has been extracted from an individually changed 64×64 cell. They never replace the per-cell baseline comparison.

The dojo-specific fallback can identify the persistent non-player sprite as the round enemy after repeated visual matches. Adding real `enemy/*.png` references makes classification explicit and should be preferred before enabling `CONTROL_ENABLED`.
