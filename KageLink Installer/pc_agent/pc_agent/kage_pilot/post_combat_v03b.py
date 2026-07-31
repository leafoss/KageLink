from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .grid_target_observer_v03 import _grid_distance
from .post_combat_v03 import (
    ChatVictoryWatcher,
    HudResourceReader,
    PostCombatDecision,
)


# Retained only as an import-compatible sentinel. There is no legacy file path,
# local calibration image or embedded fallback in the RAW-only pipeline.
DEFAULT_LEADER_TEMPLATE_PATH = None


@dataclass(frozen=True, slots=True)
class LeaderMatchV2:
    score: float
    bbox: tuple[int, int, int, int]
    foot: tuple[float, float]
    source: str = "visual"
    scale: float = 1.0


class CalibratedDojoLeaderDetector:
    """Compatibility constructor that always returns the immutable RAW matcher.

    The historic name is kept for imports only. No calibration, grayscale,
    resizing, generated scale, local file, or embedded fallback is permitted.
    """

    def __new__(
        cls,
        *,
        threshold: float = 0.88,
        template_path=None,
        memory_seconds: float = 180.0,
        scales=(1.0,),
        template_root=None,
    ):
        from .dojo_raw_trainer_v351 import RawDojoLeaderDetector

        return RawDojoLeaderDetector(
            threshold=threshold,
            template_path=template_path,
            memory_seconds=memory_seconds,
            scales=scales,
            template_root=template_root,
        )


class CalibratedHudResourceReader(HudResourceReader):
    """Real Micro-PC HUD calibration; unrelated to Trainer image matching."""

    HEALTH_FULL_PX_960 = 47.0
    CHAKRA_FULL_PX_960 = 40.0


class PostCombatRecoveryEngineV2:
    """Victory -> immutable RAW leader -> V toggle recovery."""

    def __init__(
        self,
        *,
        leader_detector=None,
        resource_reader: CalibratedHudResourceReader | None = None,
        leader_confirm_frames: int = 2,
        health_target: float = 0.90,
        chakra_target: float = 0.50,
        recovery_confirm_frames: int = 3,
        min_meditation_seconds: float = 0.75,
    ) -> None:
        self.leader_detector = leader_detector or CalibratedDojoLeaderDetector()
        self.resource_reader = resource_reader or CalibratedHudResourceReader()
        self.leader_confirm_frames = max(2, min(8, int(leader_confirm_frames)))
        self.health_target = max(0.0, min(1.0, float(health_target)))
        self.chakra_target = max(0.0, min(1.0, float(chakra_target)))
        self.recovery_confirm_frames = max(2, min(12, int(recovery_confirm_frames)))
        self.min_meditation_seconds = max(0.25, min(5.0, float(min_meditation_seconds)))
        self.state = "SEEK_LEADER"
        self._leader_cell: tuple[int, int] | None = None
        self._leader_hits = 0
        self._recovery_hits = 0
        self._meditation_started_at: float | None = None

    @staticmethod
    def _cell_for_full(point, observer) -> tuple[int, int]:
        size = float(observer.tile_size)
        origin_x, origin_y = observer.grid_origin
        return (
            math.floor((float(point[0]) - float(origin_x)) / size),
            math.floor((float(point[1]) - float(origin_y)) / size),
        )

    @staticmethod
    def _direction(player_cell, leader_cell) -> str:
        dx = int(leader_cell[0] - player_cell[0])
        dy = int(leader_cell[1] - player_cell[1])
        if abs(dx) >= abs(dy) and dx != 0:
            return "right" if dx > 0 else "left"
        if dy != 0:
            return "down" if dy > 0 else "up"
        return ""

    def step(self, frame_bgr: np.ndarray, observer_state, observer, *, now: float) -> PostCombatDecision:
        now = float(now)
        if self.state == "READY":
            return PostCombatDecision(state="READY", reason="recovery complete / recuperacao concluida")

        if self.state == "SEEK_LEADER":
            match = self.leader_detector.find(
                frame_bgr,
                arena_rect=observer_state.arena_rect,
                flow=getattr(observer_state, "global_flow", None),
                now=now,
            )
            if match is None:
                self._leader_cell = None
                self._leader_hits = 0
                return PostCombatDecision(
                    state=self.state,
                    reason="dojo leader not visible and no memory / lider nao visivel e sem memoria",
                )

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
            else:
                self._leader_hits = 0

            if match.source == "visual" and self._leader_hits < self.leader_confirm_frames:
                return PostCombatDecision(
                    state=self.state,
                    leader_score=match.score,
                    leader_distance=distance,
                    reason="confirming RAW dojo leader / confirmando lider RAW",
                )

            if distance <= 1:
                if match.source != "visual":
                    return PostCombatDecision(
                        state=self.state,
                        leader_score=match.score,
                        leader_distance=distance,
                        reason="memory says adjacent; waiting for visual confirmation / memoria adjacente; aguardando visual",
                    )
                self.state = "MEDITATING"
                self._meditation_started_at = now
                self._recovery_hits = 0
                return PostCombatDecision(
                    state="START_MEDITATION",
                    tap_v=True,
                    leader_score=match.score,
                    leader_distance=distance,
                    reason="visually adjacent to RAW dojo leader; toggle V on / adjacente visual RAW; ligar V",
                )

            direction = self._direction(player_cell, leader_cell)
            return PostCombatDecision(
                state=self.state,
                move_pulse=direction or None,
                leader_score=match.score,
                leader_distance=distance,
                reason=(
                    f"move toward RAW dojo leader ({match.source}) / mover ate lider RAW "
                    f"({match.source}): {direction or 'hold'}"
                ),
            )

        if self.state == "MEDITATING":
            levels = self.resource_reader.read(frame_bgr)
            elapsed = now - float(self._meditation_started_at or now)
            ready = (
                levels.valid
                and elapsed >= self.min_meditation_seconds
                and float(levels.health or 0.0) >= self.health_target
                and float(levels.chakra or 0.0) >= self.chakra_target
            )
            self._recovery_hits = self._recovery_hits + 1 if ready else 0

            if self._recovery_hits >= self.recovery_confirm_frames:
                self.state = "READY"
                return PostCombatDecision(
                    state="READY",
                    tap_v=True,
                    health=levels.health,
                    chakra=levels.chakra,
                    reason="recovery thresholds reached; toggle V off / recuperado; desligar V",
                )

            return PostCombatDecision(
                state=self.state,
                health=levels.health,
                chakra=levels.chakra,
                reason=(
                    f"meditating HP={float(levels.health or 0.0)*100:.0f}% "
                    f"Chakra={float(levels.chakra or 0.0)*100:.0f}%"
                ),
            )

        return PostCombatDecision(state=self.state, reason="unknown post-combat state")


__all__ = [
    "ChatVictoryWatcher",
    "CalibratedDojoLeaderDetector",
    "CalibratedHudResourceReader",
    "DEFAULT_LEADER_TEMPLATE_PATH",
    "LeaderMatchV2",
    "PostCombatRecoveryEngineV2",
]
