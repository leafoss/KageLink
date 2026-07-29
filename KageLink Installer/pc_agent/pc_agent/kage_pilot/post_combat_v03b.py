from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Iterable

import cv2
import numpy as np

from .grid_target_observer_v03 import _grid_distance
from .post_combat_v03 import (
    ChatVictoryWatcher,
    DojoLeaderDetector as EmbeddedDojoLeaderDetector,
    HudResourceReader,
    PostCombatDecision,
)


PC_AGENT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEADER_TEMPLATE_PATH = PC_AGENT_ROOT / "data" / "kage_pilot" / "dojo_leader_template.png"


@dataclass(frozen=True, slots=True)
class LeaderMatchV2:
    score: float
    bbox: tuple[int, int, int, int]
    foot: tuple[float, float]
    source: str = "visual"
    scale: float = 1.0


class CalibratedDojoLeaderDetector:
    """Prefer a locally taught live-game template and retain camera-relative memory.

    A visual match is authoritative. When the sprite is briefly hidden or leaves the frame,
    the last confirmed bounding box is shifted by the observer's global camera flow. Memory
    may guide movement but the recovery engine never starts meditation from memory alone.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.72,
        template_path: Path | str | None = None,
        memory_seconds: float = 15.0,
        scales: Iterable[float] = (0.90, 0.95, 1.00, 1.05, 1.10),
    ) -> None:
        self.threshold = max(0.45, min(0.98, float(threshold)))
        self.template_path = Path(template_path) if template_path is not None else DEFAULT_LEADER_TEMPLATE_PATH
        self.memory_seconds = max(1.0, min(60.0, float(memory_seconds)))
        normalized_scales = sorted({max(0.70, min(1.30, float(value))) for value in scales})
        self.scales = tuple(normalized_scales or (1.0,))

        local = cv2.imread(str(self.template_path), cv2.IMREAD_COLOR) if self.template_path.exists() else None
        if local is not None and local.size > 0:
            self.template = local
            self.template_source = "local"
        else:
            fallback = EmbeddedDojoLeaderDetector(threshold=0.45)
            self.template = fallback.template.copy()
            self.template_source = "embedded-fallback"

        self.template_gray = cv2.cvtColor(self.template, cv2.COLOR_BGR2GRAY)
        self._last_visual: LeaderMatchV2 | None = None
        self._last_visual_at = -1e9
        self.last_raw_score = -1.0
        self.last_raw_scale = 1.0
        self.last_raw_location: tuple[int, int] | None = None

    @staticmethod
    def _roi(frame_bgr: np.ndarray, arena_rect=None):
        frame_h, frame_w = frame_bgr.shape[:2]
        if arena_rect is None:
            x0, y0, x1, y1 = 0, 0, frame_w, frame_h
        else:
            x0, y0, x1, y1 = (int(value) for value in arena_rect)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(frame_w, x1), min(frame_h, y1)
        return frame_bgr[y0:y1, x0:x1], x0, y0

    def _best_visual(self, frame_bgr: np.ndarray, *, arena_rect=None) -> LeaderMatchV2 | None:
        roi, offset_x, offset_y = self._roi(frame_bgr, arena_rect)
        if roi.size == 0:
            return None
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        best_score = -1.0
        best_scale = 1.0
        best_location: tuple[int, int] | None = None
        best_size: tuple[int, int] | None = None

        original_h, original_w = self.template_gray.shape[:2]
        for scale in self.scales:
            width = max(8, round(original_w * scale))
            height = max(8, round(original_h * scale))
            if width > gray.shape[1] or height > gray.shape[0]:
                continue
            interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
            template = cv2.resize(self.template_gray, (width, height), interpolation=interpolation)
            result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(result)
            score = float(score)
            if score > best_score:
                best_score = score
                best_scale = scale
                best_location = (int(location[0]), int(location[1]))
                best_size = (width, height)

        self.last_raw_score = best_score
        self.last_raw_scale = best_scale
        self.last_raw_location = (
            (offset_x + best_location[0], offset_y + best_location[1])
            if best_location is not None
            else None
        )
        if best_location is None or best_size is None or best_score < self.threshold:
            return None

        left = offset_x + best_location[0]
        top = offset_y + best_location[1]
        width, height = best_size
        return LeaderMatchV2(
            score=best_score,
            bbox=(left, top, width, height),
            foot=(left + width * 0.50, top + height * 0.88),
            source="visual",
            scale=best_scale,
        )

    @staticmethod
    def _shift(match: LeaderMatchV2, flow) -> LeaderMatchV2:
        dx = float(getattr(flow, "dx", 0.0) or 0.0)
        dy = float(getattr(flow, "dy", 0.0) or 0.0)
        left, top, width, height = match.bbox
        shifted_left = round(left + dx)
        shifted_top = round(top + dy)
        return LeaderMatchV2(
            score=match.score,
            bbox=(shifted_left, shifted_top, width, height),
            foot=(match.foot[0] + dx, match.foot[1] + dy),
            source="memory",
            scale=match.scale,
        )

    def find(self, frame_bgr: np.ndarray, *, arena_rect=None, flow=None, now: float | None = None):
        timestamp = time.monotonic() if now is None else float(now)

        if self._last_visual is not None and flow is not None:
            self._last_visual = self._shift(self._last_visual, flow)

        visual = self._best_visual(frame_bgr, arena_rect=arena_rect)
        if visual is not None:
            self._last_visual = visual
            self._last_visual_at = timestamp
            return visual

        if self._last_visual is not None and timestamp - self._last_visual_at <= self.memory_seconds:
            remembered = self._last_visual
            return LeaderMatchV2(
                score=remembered.score,
                bbox=remembered.bbox,
                foot=remembered.foot,
                source="memory",
                scale=remembered.scale,
            )
        return None


class CalibratedHudResourceReader(HudResourceReader):
    """Real Micro-PC calibration: 47 health pixels and 40 chakra pixels are full."""

    HEALTH_FULL_PX_960 = 47.0
    CHAKRA_FULL_PX_960 = 40.0


class PostCombatRecoveryEngineV2:
    """Victory -> calibrated leader -> V toggle recovery, with camera-flow memory."""

    def __init__(
        self,
        *,
        leader_detector: CalibratedDojoLeaderDetector | None = None,
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
                # Camera memory guides walking, but it never counts toward V authorization.
                self._leader_hits = 0

            if match.source == "visual" and self._leader_hits < self.leader_confirm_frames:
                return PostCombatDecision(
                    state=self.state,
                    leader_score=match.score,
                    leader_distance=distance,
                    reason="confirming calibrated dojo leader / confirmando lider calibrado",
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
                    reason="visually adjacent to dojo leader; toggle V on / adjacente visual; ligar V",
                )

            direction = self._direction(player_cell, leader_cell)
            return PostCombatDecision(
                state=self.state,
                move_pulse=direction or None,
                leader_score=match.score,
                leader_distance=distance,
                reason=(
                    f"move toward dojo leader ({match.source}) / mover ate lider ({match.source}): "
                    f"{direction or 'hold'}"
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
