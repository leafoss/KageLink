from __future__ import annotations

import base64
from dataclasses import dataclass
import re

import cv2
import numpy as np

from pc_agent.chat_reader import ChatReader, find_new_lines
from .grid_target_observer_v03 import _grid_distance


# Real user-supplied Dojo leader reference. Kept as text so the GitHub contents API can
# preserve the exact PNG without adding a binary-file dependency to this incremental gate.
_DOJO_LEADER_PNG_BASE64 = (
    "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"
)

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
        # Fail closed on chat resynchronization: the returned block may contain old history.
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


class DojoLeaderDetector:
    """Exact-sprite template detector for the fixed Dojo leader supplied by the user."""

    def __init__(self, *, threshold: float = 0.72) -> None:
        raw = np.frombuffer(base64.b64decode(_DOJO_LEADER_PNG_BASE64), dtype=np.uint8)
        template = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if template is None or template.size == 0:
            raise RuntimeError("DOJO_LEADER_TEMPLATE_DECODE_FAILED")
        self.template = template
        self.template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        self.threshold = max(0.45, min(0.98, float(threshold)))

    def find(self, frame_bgr: np.ndarray, *, arena_rect=None) -> LeaderMatch | None:
        if frame_bgr is None or frame_bgr.size == 0:
            return None
        frame_h, frame_w = frame_bgr.shape[:2]
        if arena_rect is None:
            x0, y0, x1, y1 = 0, 0, frame_w, frame_h
        else:
            x0, y0, x1, y1 = (int(v) for v in arena_rect)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(frame_w, x1), min(frame_h, y1)
        roi = frame_bgr[y0:y1, x0:x1]
        th, tw = self.template_gray.shape[:2]
        if roi.shape[0] < th or roi.shape[1] < tw:
            return None
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(gray, self.template_gray, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        score = float(score)
        if score < self.threshold:
            return None
        left = x0 + int(location[0])
        top = y0 + int(location[1])
        # The supplied crop contains a little ground below the sprite. 0.84 lands at the
        # character's feet rather than the bottom edge of that ground patch.
        foot = (left + tw * 0.50, top + th * 0.84)
        return LeaderMatch(score=score, bbox=(left, top, tw, th), foot=foot)


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
    """Read HP and Chakra fill from the fixed 960x540 GAME HUD.

    The ranges are intentionally broad normalized ROIs; the actual fill is extracted by
    color. Full-fill widths are conservative so the recovery gate tends to overshoot rather
    than exit meditation below the user's requested thresholds.
    """

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
    """Deterministic victory -> leader -> meditation -> READY state machine."""

    def __init__(
        self,
        *,
        leader_detector: DojoLeaderDetector | None = None,
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
