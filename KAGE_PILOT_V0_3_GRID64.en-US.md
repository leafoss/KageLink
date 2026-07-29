# Kage Pilot v0.3 — 64 px GRID and confirmed Contact Memory

## Real-game evidence

Shinobi Story Online validation showed the previous 32 px GRID visually cutting through character heads/bodies. Reference images with two characters in vertically adjacent cells indicate that one character occupies approximately a 64 px band.

The v0.3 working hypothesis is now:

```text
visual/logical cell = 64 x 64 px
```

It remains configurable through `--grid-size`.

## Automatic alignment

The GRID origin is no longer assumed to be frame `(0,0)`. By default, the Observer offsets the lattice so `PLAYER #000` sits at the center of one 64 px cell.

When PLAYER is recalibrated with a left click, the GRID is realigned on the next frame without clearing learned environmental memory.

Manual diagnostics remain available through:

```text
--grid-origin-x
--grid-origin-y
```

Both values must be provided together.

## Confirmed CONTACT MEMORY

A single noisy contour near PLAYER must not immediately open combat memory.

The default rule now requires 2 coherent frames in the same adjacent side/cell before a new contact can open `CONTACT MEMORY`.

A previously validated TARGET can still be preserved while melee degrades the visual contour, and `CONTACT_REBIND` may still associate a replacement nearby contour while the contact window remains valid.

## Hybrid architecture

```text
OpenCV / contours
        +
Lucas-Kanade
        +
Entity Tracker
        +
Dynamic Background
        +
aligned 64x64 GRID
        +
confirmed Contact Memory
        ↓
logical TARGET
```

The Observer remains read-only and sends no keyboard input to the game.
