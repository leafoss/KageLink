from __future__ import annotations

from dataclasses import dataclass, field

from .post_combat_v03c import (
    PersistentDojoLeaderDetector,
    PostCombatRecoveryEngineV3,
)


@dataclass(slots=True)
class ConcentricCellRingSearch:
    """Deterministic concentric search around the point where post-combat begins.

    On an orthogonal tile grid, each radius is represented by a Chebyshev-distance square
    ring. Radius 1 is completely traversed before radius 2 begins, then radius 3, and so on.
    Every output is a short arrow pulse; no direction is ever held.

    The configured 30x24 arena is used only as a conservative search cap. From an unknown
    starting cell, the farthest possible arena cell is at most max(width-1, height-1) tiles
    away in Chebyshev distance, which is 29 tiles for a 30x24 arena.
    """

    pulses_per_cell: int = 4
    arena_width_cells: int = 30
    arena_height_cells: int = 24
    max_radius: int | None = None

    radius: int = field(init=False, default=1)
    completed_rings: int = field(init=False, default=0)
    visited_logical_cells: int = field(init=False, default=0)
    exhausted: bool = field(init=False, default=False)
    _segments: list[tuple[str, int]] = field(init=False, default_factory=list, repr=False)
    _segment_index: int = field(init=False, default=0, repr=False)
    _cells_remaining: int = field(init=False, default=0, repr=False)
    _pulses_remaining: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        self.pulses_per_cell = max(1, min(10, int(self.pulses_per_cell)))
        self.arena_width_cells = max(2, min(200, int(self.arena_width_cells)))
        self.arena_height_cells = max(2, min(200, int(self.arena_height_cells)))
        inferred = max(self.arena_width_cells - 1, self.arena_height_cells - 1)
        self.max_radius = inferred if self.max_radius is None else max(1, min(300, int(self.max_radius)))
        self.reset()

    def reset(self) -> None:
        self.radius = 1
        self.completed_rings = 0
        self.visited_logical_cells = 0
        self.exhausted = False
        self._segments = []
        self._segment_index = 0
        self._cells_remaining = 0
        self._pulses_remaining = 0
        self._load_ring()

    def _load_ring(self) -> None:
        if self.radius > int(self.max_radius or 1):
            self.exhausted = True
            self._segments = []
            return

        r = int(self.radius)
        # Starting at the previous ring's top midpoint:
        #   1) step outward one cell;
        #   2) trace the complete perimeter clockwise;
        #   3) finish again at the top midpoint, ready to expand one cell outward.
        self._segments = [
            ("up", 1),
            ("right", r),
            ("down", 2 * r),
            ("left", 2 * r),
            ("up", 2 * r),
            ("right", r),
        ]
        self._segment_index = 0
        self._start_segment()

    def _start_segment(self) -> None:
        if self._segment_index >= len(self._segments):
            self.completed_rings += 1
            self.radius += 1
            self._load_ring()
            return
        _, cells = self._segments[self._segment_index]
        self._cells_remaining = max(0, int(cells))
        self._pulses_remaining = self.pulses_per_cell

    @property
    def phase(self) -> str:
        if self.exhausted or not self._segments:
            return "done"
        direction, _ = self._segments[self._segment_index]
        return direction

    @property
    def progress_text(self) -> str:
        return (
            f"ring={self.radius}/{self.max_radius} phase={self.phase} "
            f"completed={self.completed_rings} cells={self.visited_logical_cells}"
        )

    def next_pulse(self) -> str | None:
        if self.exhausted:
            return None

        while not self.exhausted:
            if self._segment_index >= len(self._segments):
                self._start_segment()
                continue

            direction, _ = self._segments[self._segment_index]
            self._pulses_remaining -= 1
            if self._pulses_remaining <= 0:
                self.visited_logical_cells += 1
                self._cells_remaining -= 1
                if self._cells_remaining <= 0:
                    self._segment_index += 1
                    self._start_segment()
                else:
                    self._pulses_remaining = self.pulses_per_cell
            return direction
        return None


class PostCombatRecoveryEngineV4(PostCombatRecoveryEngineV3):
    """Persistent trainer anchor plus deterministic concentric cell-ring fallback search."""

    def __init__(
        self,
        *,
        leader_detector: PersistentDojoLeaderDetector | None = None,
        arena_width_cells: int = 30,
        arena_height_cells: int = 24,
        search_pulses_per_cell: int = 4,
        search_max_radius: int | None = None,
        search_timeout_seconds: float = 240.0,
        **kwargs,
    ) -> None:
        super().__init__(
            leader_detector=leader_detector,
            search_timeout_seconds=min(120.0, float(search_timeout_seconds)),
            search_pulses_per_tile=search_pulses_per_cell,
            search_max_radius_tiles=max(2, min(16, max(arena_width_cells, arena_height_cells))),
            **kwargs,
        )
        # v0.3c capped fallback search at 120 seconds. The known 30x24 arena may require a
        # longer deterministic route, so v0.3d intentionally widens only this post-combat cap.
        self.search_timeout_seconds = max(5.0, min(600.0, float(search_timeout_seconds)))
        self.search = ConcentricCellRingSearch(
            pulses_per_cell=search_pulses_per_cell,
            arena_width_cells=arena_width_cells,
            arena_height_cells=arena_height_cells,
            max_radius=search_max_radius,
        )

    def _search_decision(self, *, now: float):
        decision = super()._search_decision(now=now)
        if decision.state != "SEARCH_LEADER":
            return decision
        # super() consumed one pulse from the replacement search object. Replace the generic
        # reason with explicit ring progress so real logs prove systematic coverage.
        return type(decision)(
            state=decision.state,
            move_pulse=decision.move_pulse,
            tap_v=decision.tap_v,
            leader_score=decision.leader_score,
            leader_distance=decision.leader_distance,
            health=decision.health,
            chakra=decision.chakra,
            reason=(
                f"concentric cell-ring search {self.search.progress_text} / "
                f"busca em aneis de celulas {self.search.progress_text}"
            ),
        )


__all__ = [
    "ConcentricCellRingSearch",
    "PostCombatRecoveryEngineV4",
]
