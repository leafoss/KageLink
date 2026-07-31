from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from .dojo_raw_trainer_v351 import RawDojoLeaderDetector


CANONICAL_FRAME_SIZE = (960, 540)
# Compatibility constant retained for callers/tests. RAW Trainer detection never
# generates intermediate scales; the only permitted value is the source scale.
AUTO_TEMPLATE_SCALES = (1.0,)

_LAST_SOURCE_WIDTH = 0
_LAST_SOURCE_HEIGHT = 0
_LAST_CONTENT_RECT = (0, 0, CANONICAL_FRAME_SIZE[0], CANONICAL_FRAME_SIZE[1])
_LAST_RAW_SCORE = -1.0
_LAST_REQUIRED_THRESHOLD = 0.97
_LAST_RAW_AT = -1e9
_LAST_GEOMETRY_SIGNATURE: tuple | None = None


def _source_fit_scale(
    source_width: int | None = None,
    source_height: int | None = None,
) -> float:
    """Compatibility helper for HUD-only code, never for Trainer templates."""

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
            version=int(value.get("version", 2)),
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
        if geometry.template_scale != 1.0:
            raise ValueError("DOJO_RAW_GEOMETRY_SCALE_MUST_BE_ONE")
        if geometry.effective_tile_size != float(geometry.template_mode):
            raise ValueError("DOJO_RAW_GEOMETRY_CELL_INVALID")
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


def effective_tile_size_for(mode: str | int, scale: float = 1.0, *, fallback: float = 32.0) -> float:
    try:
        value = str(mode).strip()
        requested_scale = float(scale)
    except (TypeError, ValueError):
        return float(fallback)
    if value not in {"32", "64"}:
        return float(fallback)
    if abs(requested_scale - 1.0) > 1e-9:
        raise ValueError("DOJO_RAW_TEMPLATE_SCALE_DENIED")
    return float(value)


def _write_geometry(mode: str, scale: float = 1.0) -> DojoGeometry | None:
    global _LAST_GEOMETRY_SIGNATURE
    if mode not in {"32", "64"}:
        return None
    if abs(float(scale) - 1.0) > 1e-9:
        raise ValueError("DOJO_RAW_TEMPLATE_SCALE_DENIED")
    left, top, width, height = _LAST_CONTENT_RECT
    value = DojoGeometry(
        version=2,
        saved_at=time.time(),
        template_mode=mode,
        template_scale=1.0,
        effective_tile_size=float(mode),
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
        value.effective_tile_size,
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
    """Find letterbox bands for non-Trainer consumers only.

    RAW Trainer matching ignores this crop and always sees the complete original
    client frame. No template pixels pass through this helper.
    """

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
    if min(top, bottom) < 2 or abs(top - bottom) > 3 or max(top, bottom) > int(height * 0.30):
        top = bottom = 0
    if min(left, right) < 2 or abs(left - right) > 3 or max(left, right) > int(width * 0.30):
        left = right = 0

    x0, y0, x1, y1 = left, top, width - right, height - bottom
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


def normalized_content_point(frame_bgr: np.ndarray, point: tuple[float, float]) -> tuple[float, float]:
    # The RAW client frame and click target share the same client-coordinate space.
    height, width = frame_bgr.shape[:2]
    x = float(point[0]) / max(1.0, float(width - 1))
    y = float(point[1]) / max(1.0, float(height - 1))
    return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))


def content_crop(frame_bgr: np.ndarray, region) -> np.ndarray:
    left, top, content_width, content_height = content_rect_for_frame(frame_bgr)
    x, y, rw, rh = region
    x0 = left + max(0, int(round(float(x) * content_width)))
    y0 = top + max(0, int(round(float(y) * content_height)))
    x1 = left + min(content_width, int(round((float(x) + float(rw)) * content_width)))
    y1 = top + min(content_height, int(round((float(y) + float(rh)) * content_height)))
    return frame_bgr[y0:y1, x0:x1]


ResolutionIndependentDojoLeaderDetector = RawDojoLeaderDetector


def _movement_match_is_plausible(*, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else float(now)
    if current - _LAST_RAW_AT > 1.5:
        return False
    return _LAST_RAW_SCORE >= max(0.90, _LAST_REQUIRED_THRESHOLD - 0.04)


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
    if bool(getattr(original, "_kagelink_raw_click", False)):
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

    click_target_from_match._kagelink_raw_click = True
    dojo_fight_v03f._click_target_from_match = click_target_from_match
    for module_name in (
        "pc_agent.kage_pilot.trainer_search_v03k",
        "pc_agent.kage_pilot.dojo_raw_trainer_v351",
    ):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "_click_target_from_match"):
            setattr(module, "_click_target_from_match", click_target_from_match)


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

    reader_class._crop = crop
    reader_class._kagelink_resolution_hud = True


def install_resolution_independent_dojo() -> None:
    """Install exact RAW matching plus coordinate bridges.

    The historical function name is retained for compatibility. It no longer
    creates alternate template sizes or modifies either supplied template.
    """

    from . import dojo_templates, dojo_templates_v35, post_combat_v03c

    dojo_templates_v35.UserDojoLeaderDetector = RawDojoLeaderDetector
    dojo_templates.UserDojoLeaderDetector = RawDojoLeaderDetector
    post_combat_v03c.PersistentDojoLeaderDetector = RawDojoLeaderDetector
    monitor_module = sys.modules.get("pc_agent.kage_pilot.dojo_position_bridge")
    if monitor_module is not None:
        setattr(monitor_module, "UserDojoLeaderDetector", RawDojoLeaderDetector)
    _install_capture_geometry_probe()
    _install_content_coordinate_bridge()
    _install_click_mapping_bridge()
    _install_hud_content_bridge()


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
    value = float(cell_size)
    if value not in {32.0, 64.0}:
        raise ValueError("DOJO_RAW_CELL_MODE_INVALID")
    ratio = value / 32.0
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

    restored = restore_tracker_state(
        tracker,
        Path(path),
        delete_after_load=delete_after_load,
    )
    if not restored:
        return False
    value = float(getattr(tracker, "cell_size", 32.0) or 32.0)
    if value not in {32.0, 64.0}:
        return False
    apply_tracker_geometry(tracker, value)
    return True


def install_runtime_geometry_bridge(runtime) -> None:
    engine_class = runtime.ClosedLoopVisualRecoveryEngine
    if bool(getattr(engine_class, "_kagelink_resolution_geometry", False)):
        return
    original_sync = engine_class._sync_cell_mode

    def sync_cell_mode(self) -> str:
        mode = self._accepted_mode()
        detector = getattr(self, "leader_detector", None)
        accepted = str(getattr(detector, "last_accepted_template_mode", "") or "")
        geometry = read_dojo_geometry()
        if accepted in {"32", "64"}:
            mode = accepted
            cell_size = float(accepted)
        elif geometry is not None:
            mode = geometry.template_mode
            cell_size = geometry.effective_tile_size
        else:
            return original_sync(self)
        if abs(float(self.position.cell_size) - cell_size) > 0.05:
            apply_tracker_geometry(self.position, cell_size)
            runtime._telemetry(
                "DOJO_CELL_GEOMETRY",
                {
                    "mode": mode,
                    "scale": "1.000",
                    "cell_size": f"{cell_size:.3f}",
                    "raw": True,
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
