from __future__ import annotations

from dataclasses import dataclass
import re

import cv2
import numpy as np

from pc_agent.chat_reader import ChatReader, find_new_lines
from .grid_target_observer_v03 import _grid_distance


_VICTORY_RE = re.compile(r"\bhas\s+been\s+knocked(?:\s*-\s*|\s+)out\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class VictorySignal:
    text: str


class ChatVictoryWatcher:
    """Watch only newly appended Shinobi chat text for the authoritative KO phrase."""

    def __init__(self, game_title: str, chat_class: str, *, reader=None) -> None:
        self.reader = reader or ChatReader(game_title, chat_class)
        self._previous = ""
        self._primed = False

    @staticmethod
    def is_victory_text(text: str) -> bool:
        return bool(_VICTORY_RE.search(str(text or "")))

    def prime(self) -> None:
        self._previous = self.reader.read_current() or ""
        self._primed = True

    def poll(self) -> VictorySignal | None:
        current = self.reader.read_current() or ""
        if not self._primed:
            self._previous = current
            self._primed = True
            return None
        lines, resynchronized = find_new_lines(self._previous, current)
        self._previous = current
        if resynchronized:
            return None
        for line in lines:
            if self.is_victory_text(line):
                return VictorySignal(text=line)
        return None


@dataclass(frozen=True, slots=True)
class LeaderMatch:
    score: float
    bbox: tuple[int, int, int, int]
    foot: tuple[float, float]
    source: str = "visual"
    scale: float = 1.0


class DojoLeaderDetector:
    """Compatibility constructor for the immutable RAW Trainer matcher.

    This module intentionally contains no embedded image, grayscale conversion,
    resize, generated mask or fallback template. Importing the implementation is
    delayed to avoid a compatibility-module cycle during startup.
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


@dataclass(frozen=True, slots=True)
class ResourceLevels:
    health: float | None
    chakra: float | None
    health_fill_px: int
    chakra_fill_px: int

    @property
    def valid(self) -> bool:
        return self.health is not None and self.chakra is not None


class HudResourceReader:
    """Read HP and Chakra fill from the fixed 960x540 GAME HUD."""

    HEALTH_ROI = (0.150, 0.800, 0.105, 0.090)
    CHAKRA_ROI = (0.585, 0.800, 0.110, 0.090)
    HEALTH_FULL_PX_960 = 46.0
    CHAKRA_FULL_PX_960 = 44.0

    @staticmethod
    def _crop(frame: np.ndarray, region) -> np.ndarray:
        h, w = frame.shape[:2]
        x, y, rw, rh = region
        x0 = max(0, int(round(x * w)))
        y0 = max(0, int(round(y * h)))
        x1 = min(w, int(round((x + rw) * w)))
        y1 = min(h, int(round((y + rh) * h)))
        return frame[y0:y1, x0:x1]

    @staticmethod
    def _longest_column_run(mask: np.ndarray) -> int:
        if mask.size == 0:
            return 0
        minimum_pixels = 2 if mask.shape[0] >= 4 else 1
        active = np.count_nonzero(mask, axis=0) >= minimum_pixels
        best = current = 0
        for value in active.tolist():
            if value:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return int(best)

    def read(self, frame_bgr: np.ndarray) -> ResourceLevels:
        if frame_bgr is None or frame_bgr.size == 0:
            return ResourceLevels(None, None, 0, 0)
        health_roi = self._crop(frame_bgr, self.HEALTH_ROI)
        chakra_roi = self._crop(frame_bgr, self.CHAKRA_ROI)

        hb, hg, hr = cv2.split(health_roi)
        health_mask = (hr >= 125) & ((hr.astype(np.int16) - hg.astype(np.int16)) >= 35) & (
            (hr.astype(np.int16) - hb.astype(np.int16)) >= 35
        )
        cb, cg, cr = cv2.split(chakra_roi)
        chakra_mask = (cb >= 110) & ((cb.astype(np.int16) - cg.astype(np.int16)) >= 20) & (
            (cb.astype(np.int16) - cr.astype(np.int16)) >= 35
        )

        health_px = self._longest_column_run(health_mask)
        chakra_px = self._longest_column_run(chakra_mask)
        scale = max(0.25, float(frame_bgr.shape[1]) / 960.0)
        health_full = self.HEALTH_FULL_PX_960 * scale
        chakra_full = self.CHAKRA_FULL_PX_960 * scale
        health = min(1.0, float(health_px) / health_full) if health_px > 0 else 0.0
        chakra = min(1.0, float(chakra_px) / chakra_full) if chakra_px > 0 else 0.0
        return ResourceLevels(health, chakra, health_px, chakra_px)


@dataclass(frozen=True, slots=True)
class PostCombatDecision:
    state: str
    move_pulse: str | None = None
    tap_v: bool = False
    leader_score: float | None = None
    leader_distance: int | None = None
    health: float | None = None
    chakra: float | None = None
    reason: str = ""


class PostCombatRecoveryEngine:
    """Deterministic victory -> RAW leader -> meditation -> READY state machine."""

    def __init__(
        self,
        *,
        leader_detector=None,
        resource_reader: HudResourceReader | None = None,
        leader_confirm_frames: int = 2,
        health_target: float = 0.90,
        chakra_target: float = 0.50,
        recovery_confirm_frames: int = 3,
        min_meditation_seconds: float = 0.75,
    ) -> None:
        self.leader_detector = leader_detector or DojoLeaderDetector()
        self.resource_reader = resource_reader or HudResourceReader()
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
            int(max(0.0, float(point[0]) - float(origin_x)) // size),
            int(max(0.0, float(point[1]) - float(origin_y)) // size),
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
            match = self.leader_detector.find(frame_bgr, arena_rect=observer_state.arena_rect)
            if match is None:
                self._leader_cell = None
                self._leader_hits = 0
                return PostCombatDecision(state=self.state, reason="dojo leader not visible / lider do dojo nao visivel")

            x0, y0, _, _ = observer_state.arena_rect
            player_full = (
                float(x0) + float(observer_state.player_center[0]),
                float(y0) + float(observer_state.player_center[1]),
            )
            player_cell = self._cell_for_full(player_full, observer)
            leader_cell = self._cell_for_full(match.foot, observer)
            distance = _grid_distance(player_cell, leader_cell)

            if leader_cell == self._leader_cell:
                self._leader_hits += 1
            else:
                self._leader_cell = leader_cell
                self._leader_hits = 1

            if self._leader_hits < self.leader_confirm_frames:
                return PostCombatDecision(
                    state=self.state,
                    leader_score=match.score,
                    leader_distance=distance,
                    reason="confirming dojo leader / confirmando lider do dojo",
                )

            if distance <= 1:
                self.state = "MEDITATING"
                self._meditation_started_at = now
                self._recovery_hits = 0
                return PostCombatDecision(
                    state="START_MEDITATION",
                    tap_v=True,
                    leader_score=match.score,
                    leader_distance=distance,
                    reason="adjacent to dojo leader; toggle V on / adjacente ao lider; ligar V",
                )

            direction = self._direction(player_cell, leader_cell)
            return PostCombatDecision(
                state=self.state,
                move_pulse=direction or None,
                leader_score=match.score,
                leader_distance=distance,
                reason=f"move toward dojo leader / mover ate lider: {direction or 'hold'}",
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
            if ready:
                self._recovery_hits += 1
            else:
                self._recovery_hits = 0

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
    "DojoLeaderDetector",
    "HudResourceReader",
    "LeaderMatch",
    "PostCombatDecision",
    "PostCombatRecoveryEngine",
    "ResourceLevels",
    "VictorySignal",
]
