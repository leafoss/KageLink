from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import sys
import time
from typing import Iterable

import cv2
import numpy as np

from .dojo_templates_v35 import UserDojoLeaderDetector as _BaseUserDojoLeaderDetector


CANONICAL_FRAME_SIZE = (960, 540)
AUTO_TEMPLATE_SCALES = (
    0.25,
    0.30,
    0.35,
    0.40,
    0.45,
    0.50,
    0.55,
    0.60,
    0.70,
    0.80,
    0.90,
    1.00,
    1.10,
    1.20,
    1.30,
    1.45,
    1.60,
    1.80,
    2.00,
    2.25,
    2.50,
)

_LAST_SOURCE_WIDTH = 0
_LAST_SOURCE_HEIGHT = 0
_LAST_CONTENT_RECT = (0, 0, CANONICAL_FRAME_SIZE[0], CANONICAL_FRAME_SIZE[1])
_LAST_RAW_SCORE = -1.0
_LAST_REQUIRED_THRESHOLD = 0.88
_LAST_RAW_AT = -1e9
_LAST_GEOMETRY_SIGNATURE: tuple | None = None


def _source_fit_scale(
    source_width: int | None = None,
    source_height: int | None = None,
) -> float:
    width = int(_LAST_SOURCE_WIDTH if source_width is None else source_width)
    height = int(_LAST_SOURCE_HEIGHT if source_height is None else source_height)
    if width <= 0 or height <= 0:
        return 1.0
    return max(
        0.10,
        min(
            1.0,
            CANONICAL_FRAME_SIZE[0] / width,
            CANONICAL_FRAME_SIZE[1] / height,
        ),
    )


def _local_app_data_root() -> Path:
    value = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if value:
        return Path(value)
    if os.name == "nt":
        return Path.home() / "AppData" / "Local"
    return Path.home() / ".local" / "share"


def canonical_dojo_geometry_path() -> Path:
    return _local_app_data_root() / "KageLink" / "data" / "kage_pilot" / "dojo_geometry.json"


@dataclass(frozen=True, slots=True)
class DojoGeometry:
    version: int
    saved_at: float
    template_mode: str
    template_scale: float
    effective_tile_size: float
    source_width: int
    source_height: int
    canonical_width: int
    canonical_height: int
    content_left: int
    content_top: int
    content_width: int
    content_height: int

    @classmethod
    def from_dict(cls, value: dict) -> "DojoGeometry":
        geometry = cls(
            version=int(value.get("version", 1)),
            saved_at=float(value.get("saved_at", 0.0) or 0.0),
            template_mode=str(value.get("template_mode") or "-"),
            template_scale=float(value.get("template_scale", 1.0) or 1.0),
            effective_tile_size=float(value.get("effective_tile_size", 32.0) or 32.0),
            source_width=int(value.get("source_width", 0) or 0),
            source_height=int(value.get("source_height", 0) or 0),
            canonical_width=int(value.get("canonical_width", CANONICAL_FRAME_SIZE[0])),
            canonical_height=int(value.get("canonical_height", CANONICAL_FRAME_SIZE[1])),
            content_left=int(value.get("content_left", value.get("crop_left", 0)) or 0),
            content_top=int(value.get("content_top", value.get("crop_top", 0)) or 0),
            content_width=int(
                value.get("content_width", value.get("crop_width", CANONICAL_FRAME_SIZE[0]))
            ),
            content_height=int(
                value.get("content_height", value.get("crop_height", CANONICAL_FRAME_SIZE[1]))
            ),
        )
        if geometry.template_mode not in {"32", "64"}:
            raise ValueError("DOJO_GEOMETRY_MODE_INVALID")
        if not 8.0 <= geometry.effective_tile_size <= 160.0:
            raise ValueError("DOJO_GEOMETRY_TILE_INVALID")
        if not 0.10 <= geometry.template_scale <= 4.0:
            raise ValueError("DOJO_GEOMETRY_SCALE_INVALID")
        if geometry.content_width <= 0 or geometry.content_height <= 0:
            raise ValueError("DOJO_GEOMETRY_CONTENT_INVALID")
        return geometry


def read_dojo_geometry(path: str | Path | None = None) -> DojoGeometry | None:
    source = Path(path) if path is not None else canonical_dojo_geometry_path()
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None
        return DojoGeometry.from_dict(value)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def reset_dojo_geometry(path: str | Path | None = None) -> None:
    global _LAST_GEOMETRY_SIGNATURE
    destination = Path(path) if path is not None else canonical_dojo_geometry_path()
    try:
        destination.unlink(missing_ok=True)
    except OSError:
        pass
    _LAST_GEOMETRY_SIGNATURE = None


def effective_tile_size_for(mode: str | int, scale: float, *, fallback: float = 32.0) -> float:
    try:
        nominal = float(str(mode).strip())
        value = nominal * float(scale)
    except (TypeError, ValueError):
        return float(fallback)
    return max(8.0, min(160.0, value))


def _write_geometry(mode: str, scale: float) -> DojoGeometry | None:
    global _LAST_GEOMETRY_SIGNATURE
    if mode not in {"32", "64"}:
        return None
    effective = effective_tile_size_for(mode, scale)
    left, top, width, height = _LAST_CONTENT_RECT
    value = DojoGeometry(
        version=1,
        saved_at=time.time(),
        template_mode=mode,
        template_scale=float(scale),
        effective_tile_size=effective,
        source_width=int(_LAST_SOURCE_WIDTH),
        source_height=int(_LAST_SOURCE_HEIGHT),
        canonical_width=CANONICAL_FRAME_SIZE[0],
        canonical_height=CANONICAL_FRAME_SIZE[1],
        content_left=int(left),
        content_top=int(top),
        content_width=int(width),
        content_height=int(height),
    )
    signature = (
        value.template_mode,
        round(value.template_scale, 4),
        round(value.effective_tile_size, 3),
        value.source_width,
        value.source_height,
        value.content_left,
        value.content_top,
        value.content_width,
        value.content_height,
    )
    if signature == _LAST_GEOMETRY_SIGNATURE:
        return value
    destination = canonical_dojo_geometry_path()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(asdict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
        _LAST_GEOMETRY_SIGNATURE = signature
    except OSError:
        return None
    return value


def _edge_run(flags: np.ndarray, *, reverse: bool = False) -> int:
    values = flags[::-1] if reverse else flags
    count = 0
    for value in values.tolist():
        if not bool(value):
            break
        count += 1
    return count


def content_rect_for_frame(frame_bgr: np.ndarray) -> tuple[int, int, int, int]:
    """Return the real game-content rectangle inside the 960x540 fit_full canvas."""

    global _LAST_CONTENT_RECT
    if frame_bgr is None or frame_bgr.size == 0:
        return _LAST_CONTENT_RECT
    height, width = frame_bgr.shape[:2]
    if height < 32 or width < 32:
        _LAST_CONTENT_RECT = (0, 0, width, height)
        return _LAST_CONTENT_RECT

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    row_p90 = np.percentile(gray, 90, axis=1)
    row_std = np.std(gray, axis=1)
    col_p90 = np.percentile(gray, 90, axis=0)
    col_std = np.std(gray, axis=0)
    dark_rows = (row_p90 <= 24.0) & (row_std <= 9.0)
    dark_cols = (col_p90 <= 24.0) & (col_std <= 9.0)

    top = _edge_run(dark_rows)
    bottom = _edge_run(dark_rows, reverse=True)
    left = _edge_run(dark_cols)
    right = _edge_run(dark_cols, reverse=True)

    # fit_full bands are symmetric and almost uniform. Ignore one-pixel dark game edges
    # and reject large/asymmetric crops so a dark map is never mistaken for letterboxing.
    if min(top, bottom) < 2 or abs(top - bottom) > 3 or max(top, bottom) > int(height * 0.30):
        top = bottom = 0
    if min(left, right) < 2 or abs(left - right) > 3 or max(left, right) > int(width * 0.30):
        left = right = 0

    x0 = left
    y0 = top
    x1 = width - right
    y1 = height - bottom
    if x1 - x0 < int(width * 0.50) or y1 - y0 < int(height * 0.50):
        _LAST_CONTENT_RECT = (0, 0, width, height)
    else:
        _LAST_CONTENT_RECT = (x0, y0, x1 - x0, y1 - y0)
    return _LAST_CONTENT_RECT


def arena_rect_for_content(frame_bgr: np.ndarray, config) -> tuple[int, int, int, int]:
    left, top, content_width, content_height = content_rect_for_frame(frame_bgr)
    local_x0 = max(0, min(content_width - 1, round(content_width * config.arena_left)))
    local_y0 = max(0, min(content_height - 1, round(content_height * config.arena_top)))
    local_x1 = max(local_x0 + 1, min(content_width, round(content_width * config.arena_right)))
    local_y1 = max(local_y0 + 1, min(content_height, round(content_height * config.arena_bottom)))
    return left + local_x0, top + local_y0, left + local_x1, top + local_y1


def normalized_content_point(
    frame_bgr: np.ndarray,
    point: tuple[float, float],
) -> tuple[float, float]:
    left, top, width, height = content_rect_for_frame(frame_bgr)
    x = (float(point[0]) - float(left)) / max(1.0, float(width - 1))
    y = (float(point[1]) - float(top)) / max(1.0, float(height - 1))
    return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))


def content_crop(frame_bgr: np.ndarray, region) -> np.ndarray:
    left, top, content_width, content_height = content_rect_for_frame(frame_bgr)
    x, y, rw, rh = region
    x0 = left + max(0, int(round(float(x) * content_width)))
    y0 = top + max(0, int(round(float(y) * content_height)))
    x1 = left + min(content_width, int(round((float(x) + float(rw)) * content_width)))
    y1 = top + min(content_height, int(round((float(y) + float(rh)) * content_height)))
    return frame_bgr[y0:y1, x0:x1]


class ResolutionIndependentDojoLeaderDetector(_BaseUserDojoLeaderDetector):
    """External-template detector with broad automatic scale calibration."""

    def __init__(
        self,
        *,
        threshold: float = 0.88,
        template_path=None,
        memory_seconds: float = 180.0,
        scales: Iterable[float] = AUTO_TEMPLATE_SCALES,
        template_root: Path | str | None = None,
    ) -> None:
        requested_scales = tuple(scales) or AUTO_TEMPLATE_SCALES
        super().__init__(
            threshold=threshold,
            template_path=template_path,
            memory_seconds=memory_seconds,
            scales=(1.0,),
            template_root=template_root,
        )
        normalized = tuple(
            sorted({max(0.20, min(3.00, float(value))) for value in requested_scales})
        ) or (1.0,)
        self._visual_templates = tuple(
            (mode, source_name, template_gray, required_threshold, normalized)
            for mode, source_name, template_gray, required_threshold, _ in self._visual_templates
        )
        self.auto_scales = normalized
        self._template_rows = tuple(
            (mode, source_name, template_gray, required_threshold)
            for mode, source_name, template_gray, required_threshold, _ in self._visual_templates
        )
        self._last_good_scale_by_mode: dict[str, float] = {}
        self._last_broad_scan_at = -1e9
        self.last_accepted_template_scale: float | None = None
        self.effective_tile_size: float | None = None

    @staticmethod
    def _nearby_scales(seed: float) -> tuple[float, ...]:
        multipliers = (0.84, 0.90, 0.95, 1.00, 1.05, 1.10, 1.18)
        return tuple(
            sorted({max(0.20, min(3.00, float(seed) * value)) for value in multipliers})
        )

    def _focused_scales(self, mode: str) -> tuple[float, ...] | None:
        seed = self._last_good_scale_by_mode.get(mode)
        geometry = read_dojo_geometry()
        if seed is None and geometry is not None and geometry.template_mode == mode:
            seed = float(geometry.template_scale)
            old_fit = _source_fit_scale(geometry.source_width, geometry.source_height)
            new_fit = _source_fit_scale()
            if old_fit > 0.0 and geometry.source_width > 0 and geometry.source_height > 0:
                seed *= new_fit / old_fit
        return None if seed is None else self._nearby_scales(seed)

    def _assign_scales(self, *, broad: bool) -> bool:
        focused_any = False
        rows = []
        for mode, source_name, template_gray, required_threshold in self._template_rows:
            scales = None if broad else self._focused_scales(mode)
            if scales is None:
                scales = self.auto_scales
            else:
                focused_any = True
            rows.append((mode, source_name, template_gray, required_threshold, scales))
        self._visual_templates = tuple(rows)
        return focused_any

    def describe(self) -> str:
        modes = ",".join(mode for mode, *_ in self._visual_templates)
        return (
            f"templates={len(self._visual_templates)} modes={modes} "
            f"threshold={self.threshold:.3f} "
            f"auto_scale={self.auto_scales[0]:.2f}..{self.auto_scales[-1]:.2f}"
        )

    def diagnostics_text(self, *, limit: int = 8) -> str:
        del limit
        effective = "-" if self.effective_tile_size is None else f"{self.effective_tile_size:.2f}px"
        return (
            f"raw={self.last_raw_score:.3f} need={self.threshold:.3f} "
            f"scale={self.last_raw_scale:.3f} mode={self.last_raw_template_mode} "
            f"effective_tile={effective} template={self.last_raw_template_source} "
            f"rejection={self.last_rejection_reason or '-'}"
        )

    def _best_visual(self, frame_bgr: np.ndarray, *, arena_rect=None):
        global _LAST_RAW_SCORE, _LAST_REQUIRED_THRESHOLD, _LAST_RAW_AT
        content_rect_for_frame(frame_bgr)
        now = time.monotonic()
        focused = self._assign_scales(broad=False)
        match = super()._best_visual(frame_bgr, arena_rect=arena_rect)
        # Once calibrated, use a cheap local scale neighborhood. Re-run a broad scan
        # periodically only when that neighborhood stops matching.
        if match is None and focused and now - self._last_broad_scan_at >= 0.80:
            self._last_broad_scan_at = now
            self._assign_scales(broad=True)
            match = super()._best_visual(frame_bgr, arena_rect=arena_rect)

        _LAST_RAW_SCORE = float(getattr(self, "last_raw_score", -1.0) or -1.0)
        _LAST_REQUIRED_THRESHOLD = float(getattr(self, "threshold", 0.88) or 0.88)
        _LAST_RAW_AT = now
        self.last_accepted_template_scale = None
        self.effective_tile_size = None
        if match is not None and getattr(match, "source", "") == "visual":
            mode = str(getattr(self, "last_accepted_template_mode", "-") or "-")
            scale = float(getattr(match, "scale", 1.0) or 1.0)
            self.last_accepted_template_scale = scale
            if mode in {"32", "64"}:
                self._last_good_scale_by_mode[mode] = scale
                self.effective_tile_size = effective_tile_size_for(mode, scale)
                _write_geometry(mode, scale)
        return match


def _movement_scale_is_plausible(*, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else float(now)
    if current - _LAST_RAW_AT > 1.5:
        return False
    floor = max(0.55, _LAST_REQUIRED_THRESHOLD - 0.18)
    return _LAST_RAW_SCORE >= floor


def _install_capture_geometry_probe() -> None:
    from . import recorder

    capture_class = recorder.WindowsGameFrameSource
    if bool(getattr(capture_class, "_kagelink_resolution_probe", False)):
        return
    original_capture = capture_class.capture

    def capture(self):
        global _LAST_SOURCE_WIDTH, _LAST_SOURCE_HEIGHT
        value = original_capture(self)
        _LAST_SOURCE_WIDTH = int(getattr(value, "source_width", 0) or 0)
        _LAST_SOURCE_HEIGHT = int(getattr(value, "source_height", 0) or 0)
        return value

    capture_class.capture = capture
    capture_class._kagelink_resolution_probe = True


def _install_content_coordinate_bridge() -> None:
    from . import entity_observer

    entity_observer.arena_rect_for_frame = arena_rect_for_content
    entity_observer._kagelink_resolution_coordinates = True

    # Patch already-imported modules that copied the function into their globals.
    for module_name in (
        "pc_agent.kage_pilot.observer_runtime_v03",
        "pc_agent.kage_pilot.observer_runtime_v03b",
        "pc_agent.kage_pilot.observer_runtime_v03c",
    ):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "arena_rect_for_frame"):
            setattr(module, "arena_rect_for_frame", arena_rect_for_content)


def _install_click_mapping_bridge() -> None:
    from . import dojo_fight_v03f
    from .dojo_fight_v03e import TrainerClickTarget

    original = dojo_fight_v03f._click_target_from_match
    if bool(getattr(original, "_kagelink_resolution_click", False)):
        return

    def click_target_from_match(match, frame, state, observer):
        target = original(match, frame, state, observer)
        left, top, width, height = match.bbox
        click_point = (
            float(left) + float(width) * 0.50,
            float(top) + float(height) * 0.48,
        )
        normalized_x, normalized_y = normalized_content_point(frame, click_point)
        return TrainerClickTarget(
            normalized_x=normalized_x,
            normalized_y=normalized_y,
            score=target.score,
            grid_distance=target.grid_distance,
            bbox=target.bbox,
        )

    click_target_from_match._kagelink_resolution_click = True
    dojo_fight_v03f._click_target_from_match = click_target_from_match
    trainer_module = sys.modules.get("pc_agent.kage_pilot.trainer_search_v03k")
    if trainer_module is not None:
        setattr(trainer_module, "_click_target_from_match", click_target_from_match)


def _install_hud_content_bridge() -> None:
    try:
        from . import post_combat_v03
    except Exception:
        return

    reader_class = post_combat_v03.HudResourceReader
    if bool(getattr(reader_class, "_kagelink_resolution_hud", False)):
        return

    @staticmethod
    def crop(frame: np.ndarray, region) -> np.ndarray:
        return content_crop(frame, region)

    def read(self, frame_bgr: np.ndarray):
        if frame_bgr is None or frame_bgr.size == 0:
            return post_combat_v03.ResourceLevels(None, None, 0, 0)
        health_roi = content_crop(frame_bgr, self.HEALTH_ROI)
        chakra_roi = content_crop(frame_bgr, self.CHAKRA_ROI)
        if health_roi.size == 0 or chakra_roi.size == 0:
            return post_combat_v03.ResourceLevels(None, None, 0, 0)

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
        _, _, content_width, _ = content_rect_for_frame(frame_bgr)
        source_scale = _source_fit_scale()
        scale = (
            source_scale
            if _LAST_SOURCE_WIDTH > 0 and _LAST_SOURCE_HEIGHT > 0
            else max(0.25, float(content_width) / 960.0)
        )
        health_full = self.HEALTH_FULL_PX_960 * scale
        chakra_full = self.CHAKRA_FULL_PX_960 * scale
        health = min(1.0, float(health_px) / health_full) if health_px > 0 else 0.0
        chakra = min(1.0, float(chakra_px) / chakra_full) if chakra_px > 0 else 0.0
        return post_combat_v03.ResourceLevels(health, chakra, health_px, chakra_px)

    reader_class._crop = crop
    reader_class.read = read
    reader_class._kagelink_resolution_hud = True


def _install_stationary_scale_gate() -> None:
    from . import dojo_fight_v03i, trainer_search_v03k
    from .dojo_fight_v03e import DojoFightRequestError

    gate_class = trainer_search_v03k.TrainerSearchMotionGate
    if not bool(getattr(gate_class, "_kagelink_resolution_gate", False)):
        original_next_action = gate_class.next_action
        original_record_search_move = gate_class.record_search_move

        def next_action(self, *, now: float):
            action, direction = original_next_action(self, now=now)
            if _movement_scale_is_plausible(now=now):
                self._kagelink_blind_moves = 0
                self._kagelink_scale_hold_started = None
                return action, direction
            if action != "SEARCH_ALLOWED":
                return action, direction
            blind_moves = int(getattr(self, "_kagelink_blind_moves", 0) or 0)
            if blind_moves < 12:
                return action, direction
            hold_started = getattr(self, "_kagelink_scale_hold_started", None)
            if hold_started is None:
                hold_started = float(now)
                self._kagelink_scale_hold_started = hold_started
            if float(now) - float(hold_started) >= 5.0:
                raise DojoFightRequestError(
                    "TRAINER_SCALE_CALIBRATION_FAILED:"
                    f"raw={_LAST_RAW_SCORE:.3f}:need={_LAST_REQUIRED_THRESHOLD:.3f}:"
                    f"range={AUTO_TEMPLATE_SCALES[0]:.2f}..{AUTO_TEMPLATE_SCALES[-1]:.2f}"
                )
            return "SCALE_CALIBRATION_HOLD", None

        def record_search_move(self, *, now: float) -> None:
            original_record_search_move(self, now=now)
            if not _movement_scale_is_plausible(now=now):
                self._kagelink_blind_moves = int(
                    getattr(self, "_kagelink_blind_moves", 0) or 0
                ) + 1

        gate_class.next_action = next_action
        gate_class.record_search_move = record_search_move
        gate_class._kagelink_resolution_gate = True

    original_search = trainer_search_v03k.search_trainer_until_visible_safe
    if not bool(getattr(original_search, "_kagelink_resolution_search", False)):

        def guarded_search(*args, **kwargs):
            global _LAST_RAW_SCORE, _LAST_REQUIRED_THRESHOLD, _LAST_RAW_AT
            _LAST_RAW_SCORE = -1.0
            _LAST_REQUIRED_THRESHOLD = float(kwargs.get("leader_threshold", 0.88) or 0.88)
            _LAST_RAW_AT = -1e9
            try:
                return original_search(*args, **kwargs)
            except DojoFightRequestError as error:
                code = str(error).split(":", 1)[0]
                if code == "TRAINER_SEARCH_TIMEOUT" and not _movement_scale_is_plausible():
                    raise DojoFightRequestError(
                        "TRAINER_SCALE_CALIBRATION_FAILED:"
                        f"raw={_LAST_RAW_SCORE:.3f}:need={_LAST_REQUIRED_THRESHOLD:.3f}:"
                        f"range={AUTO_TEMPLATE_SCALES[0]:.2f}..{AUTO_TEMPLATE_SCALES[-1]:.2f}"
                    ) from error
                raise

        guarded_search._kagelink_resolution_search = True
        trainer_search_v03k.search_trainer_until_visible_safe = guarded_search
        dojo_fight_v03i.search_trainer_until_visible = guarded_search


def install_resolution_independent_dojo() -> None:
    """Install content-aware coordinates, auto-scale Trainer and fail-closed search."""

    from . import dojo_templates, dojo_templates_v35, post_combat_v03c

    dojo_templates_v35.UserDojoLeaderDetector = ResolutionIndependentDojoLeaderDetector
    dojo_templates.UserDojoLeaderDetector = ResolutionIndependentDojoLeaderDetector
    post_combat_v03c.PersistentDojoLeaderDetector = ResolutionIndependentDojoLeaderDetector

    monitor_module = sys.modules.get("pc_agent.kage_pilot.dojo_position_bridge")
    if monitor_module is not None:
        setattr(monitor_module, "UserDojoLeaderDetector", ResolutionIndependentDojoLeaderDetector)

    _install_capture_geometry_probe()
    _install_content_coordinate_bridge()
    _install_click_mapping_bridge()
    _install_hud_content_bridge()
    _install_stationary_scale_gate()


def geometry_cli_args(geometry: DojoGeometry | None = None) -> list[str]:
    value = geometry or read_dojo_geometry()
    if value is None:
        return []
    ratio = max(0.25, min(4.0, value.effective_tile_size / 32.0))
    return [
        "--grid-size",
        f"{value.effective_tile_size:.4f}",
        "--player-box-width",
        f"{max(6.0, min(80.0, 18.0 * ratio)):.4f}",
        "--player-box-height",
        f"{max(10.0, min(120.0, 38.0 * ratio)):.4f}",
        "--match-distance",
        f"{max(20.0, min(360.0, 105.0 * ratio)):.4f}",
    ]


def apply_tracker_geometry(tracker, cell_size: float) -> float:
    value = max(8.0, min(160.0, float(cell_size)))
    ratio = max(0.25, min(4.0, value / 32.0))
    tracker.cell_size = value
    tracker.odometry.cell_size = value
    tracker.odometry.player_patch_width = max(8, min(88, round(22.0 * ratio)))
    tracker.odometry.player_patch_height = max(12, min(152, round(38.0 * ratio)))
    tracker.odometry.reset()
    return value


def restore_tracker_state_resolution_safe(
    tracker,
    path: str | Path,
    *,
    delete_after_load: bool = False,
) -> bool:
    from .dojo_position_bridge import restore_tracker_state

    source = Path(path)
    intended_cell_size: float | None = None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        position = payload.get("position") if isinstance(payload, dict) else None
        if isinstance(position, dict):
            intended_cell_size = max(
                8.0,
                min(160.0, float(position.get("cell_size", 32.0) or 32.0)),
            )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        intended_cell_size = None

    restored = restore_tracker_state(
        tracker,
        source,
        delete_after_load=delete_after_load,
    )
    if not restored:
        return False
    if intended_cell_size is not None:
        apply_tracker_geometry(tracker, intended_cell_size)
    return True


def install_runtime_geometry_bridge(runtime) -> None:
    engine_class = runtime.ClosedLoopVisualRecoveryEngine
    if bool(getattr(engine_class, "_kagelink_resolution_geometry", False)):
        return
    original_sync = engine_class._sync_cell_mode

    def sync_cell_mode(self) -> str:
        mode = self._accepted_mode()
        detector = getattr(self, "leader_detector", None)
        scale = getattr(detector, "last_accepted_template_scale", None)
        geometry = read_dojo_geometry()
        if mode in {"32", "64"} and scale is not None:
            cell_size = effective_tile_size_for(mode, float(scale))
        elif geometry is not None:
            mode = geometry.template_mode
            cell_size = geometry.effective_tile_size
        else:
            return original_sync(self)
        if abs(float(self.position.cell_size) - float(cell_size)) > 0.05:
            apply_tracker_geometry(self.position, float(cell_size))
            effective_scale = float(scale if scale is not None else geometry.template_scale)
            runtime._telemetry(
                "DOJO_CELL_GEOMETRY",
                {
                    "mode": mode,
                    "scale": f"{effective_scale:.3f}",
                    "cell_size": f"{float(cell_size):.3f}",
                },
            )
        return mode

    engine_class._sync_cell_mode = sync_cell_mode
    engine_class._kagelink_resolution_geometry = True


__all__ = [
    "AUTO_TEMPLATE_SCALES",
    "CANONICAL_FRAME_SIZE",
    "DojoGeometry",
    "ResolutionIndependentDojoLeaderDetector",
    "apply_tracker_geometry",
    "arena_rect_for_content",
    "canonical_dojo_geometry_path",
    "content_crop",
    "content_rect_for_frame",
    "effective_tile_size_for",
    "geometry_cli_args",
    "install_resolution_independent_dojo",
    "install_runtime_geometry_bridge",
    "normalized_content_point",
    "read_dojo_geometry",
    "reset_dojo_geometry",
    "restore_tracker_state_resolution_safe",
]
