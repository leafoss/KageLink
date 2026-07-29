from __future__ import annotations

from dataclasses import dataclass
import math

from .grid_target_observer_v03 import _grid_distance
from .post_combat_v03 import PostCombatDecision
from .post_combat_v03b import (
    CalibratedDojoLeaderDetector,
    CalibratedHudResourceReader,
    PostCombatRecoveryEngineV2,
)


class PersistentDojoLeaderDetector(CalibratedDojoLeaderDetector):
    """Keep a calibrated Dojo anchor through a full fight.

    The v0.3b detector intentionally used a short memory. For the complete Dojo loop we
    preserve the last visual trainer anchor for the whole fight and shift it by global camera
    flow on every combat frame. Memory may guide walking but never authorizes meditation.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.72,
        template_path=None,
        memory_seconds: float = 180.0,
        scales=(0.90, 0.95, 1.00, 1.05, 1.10),
    ) -> None:
        # The local calibrated template scored >=0.93 in the real probe. Raising the effective
        # floor protects the long-lived world anchor from combat-particle false matches.
        effective_threshold = max(0.88, float(threshold))
        super().__init__(
            threshold=effective_threshold,
            template_path=template_path,
            memory_seconds=min(60.0, float(memory_seconds)),
            scales=scales,
        )
        self.memory_seconds = max(30.0, min(300.0, float(memory_seconds)))

    @property
    def has_anchor(self) -> bool:
        return self._last_visual is not None


@dataclass
class ExpandingSquareSearch:
    """Bounded dead-man search used only when no trainer anchor exists.

    The sequence walks an expanding square around the current position. Every returned item is
    one short arrow pulse; no direction is ever held. Visual matching is retried before each
    pulse, so the search stops as soon as the trainer re-enters the frame.
    """

    pulses_per_tile: int = 4
    max_radius_tiles: int = 8

    def __post_init__(self) -> None:
        self.pulses_per_tile = max(2, min(10, int(self.pulses_per_tile)))
        self.max_radius_tiles = max(2, min(16, int(self.max_radius_tiles)))
        self.reset()

    def reset(self) -> None:
        self._directions = ("up", "right", "down", "left")
        self._direction_index = 0
        self._leg_tiles = 1
        self._completed_legs = 0
        self._remaining_pulses = self.pulses_per_tile
        self.exhausted = False

    def next_pulse(self) -> str | None:
        if self.exhausted:
            return None
        direction = self._directions[self._direction_index]
        self._remaining_pulses -= 1
        if self._remaining_pulses <= 0:
            self._direction_index = (self._direction_index + 1) % len(self._directions)
            self._completed_legs += 1
            if self._completed_legs % 2 == 0:
                self._leg_tiles += 1
            if self._leg_tiles > self.max_radius_tiles:
                self.exhausted = True
            else:
                self._remaining_pulses = self._leg_tiles * self.pulses_per_tile
        return direction


class PostCombatRecoveryEngineV3(PostCombatRecoveryEngineV2):
    """Trainer anchor return first, bounded visual search second, meditation last.

    Memory may navigate but never authorizes ``V``. When memory claims adjacency for too long,
    the engine deliberately ignores that memory and performs a bounded visual reacquisition
    search. Two nearby current visual observations may authorize meditation even when camera/grid
    jitter places the same trainer foot in neighboring cells.
    """

    def __init__(
        self,
        *,
        leader_detector: PersistentDojoLeaderDetector | None = None,
        resource_reader: CalibratedHudResourceReader | None = None,
        leader_confirm_frames: int = 2,
        health_target: float = 0.90,
        chakra_target: float = 0.50,
        recovery_confirm_frames: int = 3,
        min_meditation_seconds: float = 0.75,
        search_delay_seconds: float = 0.75,
        search_timeout_seconds: float = 45.0,
        search_pulses_per_tile: int = 4,
        search_max_radius_tiles: int = 8,
        adjacent_visual_radius_px: float = 48.0,
        adjacent_visual_window_seconds: float = 1.25,
        adjacent_memory_reacquire_seconds: float = 1.0,
    ) -> None:
        detector = leader_detector or PersistentDojoLeaderDetector()
        super().__init__(
            leader_detector=detector,
            resource_reader=resource_reader or CalibratedHudResourceReader(),
            leader_confirm_frames=leader_confirm_frames,
            health_target=health_target,
            chakra_target=chakra_target,
            recovery_confirm_frames=recovery_confirm_frames,
            min_meditation_seconds=min_meditation_seconds,
        )
        self.search_delay_seconds = max(0.25, min(5.0, float(search_delay_seconds)))
        self.search_timeout_seconds = max(5.0, min(120.0, float(search_timeout_seconds)))
        self.search = ExpandingSquareSearch(
            pulses_per_tile=search_pulses_per_tile,
            max_radius_tiles=search_max_radius_tiles,
        )
        self.adjacent_visual_radius_px = max(8.0, min(96.0, float(adjacent_visual_radius_px)))
        self.adjacent_visual_window_seconds = max(
            0.25,
            min(3.0, float(adjacent_visual_window_seconds)),
        )
        self.adjacent_memory_reacquire_seconds = max(
            0.25,
            min(5.0, float(adjacent_memory_reacquire_seconds)),
        )
        self._search_started_at: float | None = None
        self._post_started = False
        self.last_combat_anchor = None
        self._adjacent_visual_hits = 0
        self._adjacent_visual_foot: tuple[float, float] | None = None
        self._adjacent_visual_seen_at = -1e9
        self._adjacent_memory_since: float | None = None
        self._visual_reacquire_mode = False

    @property
    def post_started(self) -> bool:
        return self._post_started

    def _reset_adjacent_visual_evidence(self) -> None:
        self._adjacent_visual_hits = 0
        self._adjacent_visual_foot = None
        self._adjacent_visual_seen_at = -1e9

    def _record_adjacent_visual(self, match, *, now: float) -> None:
        foot = (float(match.foot[0]), float(match.foot[1]))
        stable = (
            self._adjacent_visual_foot is not None
            and float(now) - self._adjacent_visual_seen_at <= self.adjacent_visual_window_seconds
            and math.hypot(
                foot[0] - self._adjacent_visual_foot[0],
                foot[1] - self._adjacent_visual_foot[1],
            )
            <= self.adjacent_visual_radius_px
        )
        self._adjacent_visual_hits = self._adjacent_visual_hits + 1 if stable else 1
        self._adjacent_visual_foot = foot
        self._adjacent_visual_seen_at = float(now)

    def begin_post_combat(self) -> None:
        self._post_started = True
        self._search_started_at = None
        self.search.reset()
        self._adjacent_memory_since = None
        self._visual_reacquire_mode = False
        self._reset_adjacent_visual_evidence()

    def observe_world(self, frame_bgr, observer_state, observer, *, now: float):
        """Read-only combat hook that keeps the trainer world anchor camera-aligned."""
        del observer
        if self._post_started or self.state != "SEEK_LEADER":
            return None
        match = self.leader_detector.find(
            frame_bgr,
            arena_rect=observer_state.arena_rect,
            flow=getattr(observer_state, "global_flow", None),
            now=float(now),
        )
        if match is not None:
            self.last_combat_anchor = match
        return match

    def _search_decision(self, *, now: float) -> PostCombatDecision:
        if self._search_started_at is None:
            self._search_started_at = float(now)
        elapsed = float(now) - self._search_started_at
        if elapsed < self.search_delay_seconds:
            return PostCombatDecision(
                state="SEARCH_WAIT",
                reason="waiting briefly for trainer visual / aguardando visao do treinador",
            )
        if elapsed >= self.search_timeout_seconds:
            return PostCombatDecision(
                state="SEARCH_HOLD",
                reason="bounded trainer search timeout / limite da busca do treinador",
            )
        direction = self.search.next_pulse()
        if direction is None:
            return PostCombatDecision(
                state="SEARCH_HOLD",
                reason="expanding-square search exhausted / busca em quadrado esgotada",
            )
        return PostCombatDecision(
            state="SEARCH_LEADER",
            move_pulse=direction,
            reason=f"bounded expanding-square search / busca limitada: {direction}",
        )

    def _visual_reacquire_decision(self, match, distance: int, *, now: float) -> PostCombatDecision:
        decision = self._search_decision(now=float(now))
        state = "REACQUIRE_LEADER_VISUAL" if decision.move_pulse is not None else "REACQUIRE_VISUAL_WAIT"
        return PostCombatDecision(
            state=state,
            move_pulse=decision.move_pulse,
            leader_score=match.score,
            leader_distance=distance,
            reason=(
                "adjacent trainer memory stalled; forcing current visual reacquisition / "
                "memoria adjacente travada; forcar nova confirmacao visual: "
                f"{decision.reason}"
            ),
        )

    def step(self, frame_bgr, observer_state, observer, *, now: float) -> PostCombatDecision:
        self._post_started = True
        now = float(now)
        if self.state != "SEEK_LEADER":
            return super().step(frame_bgr, observer_state, observer, now=now)

        match = self.leader_detector.find(
            frame_bgr,
            arena_rect=observer_state.arena_rect,
            flow=getattr(observer_state, "global_flow", None),
            now=now,
        )
        if match is None:
            self._leader_cell = None
            self._leader_hits = 0
            if now - self._adjacent_visual_seen_at > self.adjacent_visual_window_seconds:
                self._reset_adjacent_visual_evidence()
            return self._search_decision(now=now)

        # A current visual always exits forced reacquisition and resets the fallback route.
        if match.source == "visual":
            self._visual_reacquire_mode = False
            self._adjacent_memory_since = None
            self._search_started_at = None
            self.search.reset()

        x0, y0, _, _ = observer_state.arena_rect
        player_full = (
            float(x0) + float(observer_state.player_center[0]),
            float(y0) + float(observer_state.player_center[1]),
        )
        player_cell = self._cell_for_full(player_full, observer)
        leader_cell = self._cell_for_full(match.foot, observer)
        distance = _grid_distance(player_cell, leader_cell)

        if match.source == "visual":
            if leader_cell == self._leader_cell:
                self._leader_hits += 1
            else:
                self._leader_cell = leader_cell
                self._leader_hits = 1
            if distance <= 1:
                self._record_adjacent_visual(match, now=now)
            else:
                self._reset_adjacent_visual_evidence()
        else:
            # Memory can return Leafos toward the trainer but can never build V authorization.
            self._leader_hits = 0
            if now - self._adjacent_visual_seen_at > self.adjacent_visual_window_seconds:
                self._reset_adjacent_visual_evidence()
            if self._visual_reacquire_mode:
                return self._visual_reacquire_decision(match, distance, now=now)

        visual_ready = (
            match.source == "visual"
            and distance <= 1
            and (
                self._leader_hits >= self.leader_confirm_frames
                or self._adjacent_visual_hits >= self.leader_confirm_frames
            )
        )

        if match.source == "visual" and self._leader_hits < self.leader_confirm_frames and not visual_ready:
            return PostCombatDecision(
                state="SEEK_LEADER",
                leader_score=match.score,
                leader_distance=distance,
                reason="confirming trainer after return/search / confirmando treinador",
            )

        if distance <= 1:
            if match.source != "visual":
                if self._adjacent_memory_since is None:
                    self._adjacent_memory_since = now
                if now - self._adjacent_memory_since >= self.adjacent_memory_reacquire_seconds:
                    self._visual_reacquire_mode = True
                    self._search_started_at = None
                    self.search.reset()
                    return self._visual_reacquire_decision(match, distance, now=now)
                return PostCombatDecision(
                    state="SEEK_LEADER",
                    leader_score=match.score,
                    leader_distance=distance,
                    reason=(
                        "memory says adjacent; visual required for V / "
                        "memoria adjacente; exige visual"
                    ),
                )
            if not visual_ready:
                return PostCombatDecision(
                    state="SEEK_LEADER",
                    leader_score=match.score,
                    leader_distance=distance,
                    reason="confirming adjacent trainer visual / confirmando treinador adjacente",
                )
            self.state = "MEDITATING"
            self._meditation_started_at = now
            self._recovery_hits = 0
            return PostCombatDecision(
                state="START_MEDITATION",
                tap_v=True,
                leader_score=match.score,
                leader_distance=distance,
                reason=(
                    "two current adjacent trainer visuals confirmed; toggle V on / "
                    "duas confirmacoes visuais adjacentes; ligar V"
                ),
            )

        self._adjacent_memory_since = None
        direction = self._direction(player_cell, leader_cell)
        return PostCombatDecision(
            state="RETURN_TO_LEADER" if match.source == "memory" else "SEEK_LEADER",
            move_pulse=direction or None,
            leader_score=match.score,
            leader_distance=distance,
            reason=(
                f"return toward trainer ({match.source}) / retornar ao treinador ({match.source}): "
                f"{direction or 'hold'}"
            ),
        )


__all__ = [
    "ExpandingSquareSearch",
    "PersistentDojoLeaderDetector",
    "PostCombatRecoveryEngineV3",
]
