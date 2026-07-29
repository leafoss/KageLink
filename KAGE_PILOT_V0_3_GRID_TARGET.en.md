# Kage Pilot v0.3 — Hybrid GRID Target

## Goal

Real validation showed two different behaviours:

- contour tracking + Lucas–Kanade performs well in combat and can preserve IDs through contact;
- animated water can still create entities and high Enemy Scores.

The GRID does not replace the previous tracker. It adds a second source of spatial evidence.

```text
contours + Lucas–Kanade + appearance + temporal memory
                         +
                  fixed 32x32 GRID
                         ↓
              movement between cells
                         ↓
              really approaches PLAYER?
                         ↓
                  TARGET eligible
```

## GRID

The initial working size is `32x32 px`, configurable with `--grid-size`.

The lattice is aligned to captured-frame origin, not arena-crop origin. This prevents cell shifts when the arena crop begins a few pixels inside the window.

## Approach evidence

For each ENTITY, recent centers are converted into grid cells. Consecutive positions inside the same cell are compressed.

The observer measures:

- current cell;
- Chebyshev distance to the PLAYER cell;
- unique cells visited;
- steps that reduced distance;
- steps that increased distance;
- net distance reduction;
- ratio of steps toward PLAYER;
- local BACKGROUND_DYNAMIC strength.

A distant trajectory only counts as coherent approach after crossing at least three cells, including at least two approach steps, positive net distance reduction, and a majority of movement toward PLAYER.

## TARGET rule

- `OCCLUDED`: eligible because contact has already been proven.
- immediately adjacent PLAYER cell: may be eligible after normal tracker persistence.
- two or more cells away: requires coherent GRID trajectory.
- strong animated-background region: remains blocked unless there is a real coherent trajectory toward PLAYER.
- Enemy Score alone cannot create TARGET.

This specifically prevents animated water from acquiring lock through motion spikes.

## CONTACT MEMORY

When a validated target reaches PLAYER adjacency or enters `OCCLUDED`, a short contact-memory window is created, initially `2.8 s`.

During this window:

- the contour may disappear;
- the visual ID may fluctuate;
- logical lock may continue as `CONTACT_MEMORY`;
- a new candidate reappearing beside PLAYER on the same side may rebind the lock as `CONTACT_REBIND`.

A `LOST` track never refreshes its own contact window. Only adjacent `VISIBLE` or `OCCLUDED` evidence can extend it.

## Overlay and telemetry

The GRID is shown over the arena by default. Hide it with:

```powershell
.\.venv-kage-pilot\Scripts\python.exe kage_pilot_observer.py --no-grid-overlay
```

Telemetry now includes:

```text
grid_active=N
target=#NNN/STATE/SIDE/SCORE
grid[cell=x,y d=N toward=N away=N net=N bg=0.xx]
```

`d` is grid-cell distance to PLAYER.

## Validation gate

Water:

```text
TARGET should remain none
```

even if ENTITYs and high Enemy Scores still exist.

Combat:

```text
distant ENTITY
  ↓
traverses cells toward PLAYER
  ↓
TARGET
  ↓
adjacent / OCCLUDED
  ↓
CONTACT MEMORY
  ↓
reappears
  ↓
same logical lock / CONTACT REBIND
```

This revision remains observation-only and sends no keys to the game.
