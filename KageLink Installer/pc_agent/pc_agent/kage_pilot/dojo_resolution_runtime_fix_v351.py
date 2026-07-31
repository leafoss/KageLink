from __future__ import annotations

import math
import sys
from typing import Iterable

import numpy as np

from . import dojo_resolution_bridge_v351 as _bridge
from .dojo_templates_v35 import DojoTemplateStore


_SCALE_BATCH_SIZE = 4
_MIN_SCALED_TEMPLATE_EDGE = 14
_CONFIG_BASELINES: dict[int, dict[str, float]] = {}
_INSTALLED = False
_ORIGINAL_RESOLUTION_DETECTOR = _bridge.ResolutionIndependentDojoLeaderDetector


class BoundedResolutionIndependentDojoLeaderDetector(_ORIGINAL_RESOLUTION_DETECTOR):
    """Resolution detector with bounded work and one active mode per frame.

    The first PR23 resolution bridge scanned every scale of every configured template
    on every frame. A 64-mode template could therefore stall startup, while very small
    scales could produce high-confidence false positives and an unusably tiny combat grid.

    This detector searches only a small batch per frame, prioritizes the scale implied by
    the real source window, and locks one mode after a valid visual hit. A focused lock is
    cheap enough to provide the consecutive confirmation frames required by the caller.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._kagelink_locked_mode: str | None = None
        self._kagelink_lock_misses = 0
        self._kagelink_mode_cursor = 0
        self._kagelink_scale_cursor: dict[str, int] = {}
        self._kagelink_scale_signature: tuple[int, int] | None = None
        self.active_scan_mode = "-"
        self.active_scan_scales: tuple[float, ...] = ()

    @staticmethod
    def _scaled_edge_is_usable(template_gray: np.ndarray, scale: float) -> bool:
        height, width = template_gray.shape[:2]
        return min(round(width * scale), round(height * scale)) >= _MIN_SCALED_TEMPLATE_EDGE

    def _ordered_plausible_scales(self, template_gray: np.ndarray) -> tuple[float, ...]:
        source_seed = max(0.20, min(1.0, float(_bridge._source_fit_scale())))
        source_signature = (
            int(getattr(_bridge, "_LAST_SOURCE_WIDTH", 0) or 0),
            int(getattr(_bridge, "_LAST_SOURCE_HEIGHT", 0) or 0),
        )
        if source_signature != self._kagelink_scale_signature:
            self._kagelink_scale_signature = source_signature
            self._kagelink_scale_cursor.clear()

        # Keep enough room for templates captured on a different machine, but reject
        # implausibly tiny candidates that collapse a character into a 8-12 px false hit.
        minimum = max(0.25, source_seed * 0.55)
        maximum = min(2.50, max(1.35, source_seed * 2.40))
        values = tuple(
            scale
            for scale in self.auto_scales
            if minimum <= float(scale) <= maximum
            and self._scaled_edge_is_usable(template_gray, float(scale))
        )
        if not values:
            values = tuple(
                scale
                for scale in self.auto_scales
                if self._scaled_edge_is_usable(template_gray, float(scale))
            )
        if not values:
            values = (1.0,)

        def priority(scale: float) -> tuple[float, float]:
            safe = max(0.01, float(scale))
            return (
                abs(math.log(safe / source_seed)),
                abs(math.log(safe)),
            )

        return tuple(sorted({float(value) for value in values}, key=priority))

    def _scale_batch(self, mode: str, template_gray: np.ndarray) -> tuple[float, ...]:
        ordered = self._ordered_plausible_scales(template_gray)
        count = len(ordered)
        cursor = int(self._kagelink_scale_cursor.get(mode, 0) or 0) % max(1, count)
        batch_count = min(_SCALE_BATCH_SIZE, count)
        batch = tuple(ordered[(cursor + offset) % count] for offset in range(batch_count))
        self._kagelink_scale_cursor[mode] = (cursor + batch_count) % max(1, count)
        return tuple(sorted(set(batch)))

    def _assign_scales(self, *, broad: bool) -> bool:
        rows = tuple(self._template_rows)
        if not rows:
            self._visual_templates = ()
            return False

        locked = self._kagelink_locked_mode
        if locked is not None and not broad:
            selected_rows = [row for row in rows if row[0] == locked]
            if selected_rows:
                output = []
                for mode, source_name, template_gray, required_threshold in selected_rows:
                    focused = self._focused_scales(mode)
                    if focused is None:
                        focused = self._scale_batch(mode, template_gray)
                    focused = tuple(
                        scale
                        for scale in focused
                        if self._scaled_edge_is_usable(template_gray, float(scale))
                    ) or self._scale_batch(mode, template_gray)
                    output.append(
                        (mode, source_name, template_gray, required_threshold, focused)
                    )
                self._visual_templates = tuple(output)
                self.active_scan_mode = locked
                self.active_scan_scales = tuple(output[0][4])
                return True

        # Scan one template mode per frame. With two configured modes, all likely
        # scales are covered in roughly one to two seconds without freezing the UI.
        modes = tuple(dict.fromkeys(str(row[0]) for row in rows))
        if locked is not None and broad and locked in modes:
            selected_mode = locked
        else:
            selected_mode = modes[self._kagelink_mode_cursor % len(modes)]
            self._kagelink_mode_cursor = (self._kagelink_mode_cursor + 1) % len(modes)

        output = []
        for mode, source_name, template_gray, required_threshold in rows:
            if str(mode) != selected_mode:
                continue
            scales = self._scale_batch(str(mode), template_gray)
            output.append((mode, source_name, template_gray, required_threshold, scales))
        self._visual_templates = tuple(output)
        self.active_scan_mode = selected_mode
        self.active_scan_scales = tuple(output[0][4]) if output else ()
        return False

    def _best_visual(self, frame_bgr: np.ndarray, *, arena_rect=None):
        match = super()._best_visual(frame_bgr, arena_rect=arena_rect)
        if match is not None and getattr(match, "source", "") == "visual":
            mode = str(getattr(self, "last_accepted_template_mode", "-") or "-")
            if mode and mode != "-":
                self._kagelink_locked_mode = mode
                self._kagelink_lock_misses = 0
        elif self._kagelink_locked_mode is not None:
            self._kagelink_lock_misses += 1
            if self._kagelink_lock_misses >= 8:
                self._kagelink_locked_mode = None
                self._kagelink_lock_misses = 0
        return match

    def describe(self) -> str:
        modes = ",".join(mode for mode, *_ in self._template_rows)
        return (
            f"templates={len(self._template_rows)} modes={modes} "
            f"threshold={self.threshold:.3f} scan=bounded-{_SCALE_BATCH_SIZE}/frame"
        )

    def diagnostics_text(self, *, limit: int = 8) -> str:
        del limit
        effective = "-" if self.effective_tile_size is None else f"{self.effective_tile_size:.2f}px"
        scales = ",".join(f"{value:.2f}" for value in self.active_scan_scales) or "-"
        return (
            f"raw={self.last_raw_score:.3f} need={self.threshold:.3f} "
            f"scale={self.last_raw_scale:.3f} mode={self.last_raw_template_mode} "
            f"scan_mode={self.active_scan_mode} scan_scales={scales} "
            f"effective_tile={effective} template={self.last_raw_template_source} "
            f"rejection={self.last_rejection_reason or '-'}"
        )


def _configured_mode_hint() -> str | None:
    try:
        records = DojoTemplateStore().records()
    except Exception:
        return None
    modes = [mode for mode in ("32", "64") if records.get(mode) is not None and records[mode].configured]
    if len(modes) == 1:
        return modes[0]
    if "32" in modes:
        # Before a visual lock, the smaller cell is the conservative search choice:
        # it shortens pulses and cannot skip across a nearby Trainer.
        return "32"
    return modes[0] if modes else None


def _desired_geometry() -> tuple[str, float, str] | None:
    geometry = _bridge.read_dojo_geometry()
    if geometry is not None:
        return geometry.template_mode, float(geometry.effective_tile_size), "confirmed-template"
    mode = _configured_mode_hint()
    source_width = int(getattr(_bridge, "_LAST_SOURCE_WIDTH", 0) or 0)
    source_height = int(getattr(_bridge, "_LAST_SOURCE_HEIGHT", 0) or 0)
    if mode is None or source_width <= 0 or source_height <= 0:
        return None
    cell_size = _bridge.effective_tile_size_for(mode, _bridge._source_fit_scale())
    return mode, max(8.0, min(160.0, float(cell_size))), "source-estimate"


def _scale_observer_config(config, ratio: float) -> None:
    key = id(config)
    baseline = _CONFIG_BASELINES.get(key)
    if baseline is None:
        baseline = {
            "min_candidate_area": float(config.min_candidate_area),
            "max_candidate_area": float(config.max_candidate_area),
            "min_candidate_width": float(config.min_candidate_width),
            "min_candidate_height": float(config.min_candidate_height),
            "max_candidate_width": float(config.max_candidate_width),
            "max_candidate_height": float(config.max_candidate_height),
            "background_cell_size": float(getattr(config, "background_cell_size", 32.0)),
            "background_neighbor_radius": float(
                getattr(config, "background_neighbor_radius", 58.0)
            ),
            "background_player_guard": float(
                getattr(config, "background_player_guard", 78.0)
            ),
            "reacquire_distance": float(getattr(config, "reacquire_distance", 180.0)),
        }
        _CONFIG_BASELINES[key] = baseline

    safe = max(0.25, min(4.0, float(ratio)))
    area_scale = safe * safe
    config.min_candidate_area = max(12.0, baseline["min_candidate_area"] * area_scale)
    config.max_candidate_area = max(450.0, baseline["max_candidate_area"] * area_scale)
    config.min_candidate_width = max(3, round(baseline["min_candidate_width"] * safe))
    config.min_candidate_height = max(5, round(baseline["min_candidate_height"] * safe))
    config.max_candidate_width = max(36, round(baseline["max_candidate_width"] * safe))
    config.max_candidate_height = max(48, round(baseline["max_candidate_height"] * safe))
    if hasattr(config, "background_cell_size"):
        config.background_cell_size = max(12.0, baseline["background_cell_size"] * safe)
    if hasattr(config, "background_neighbor_radius"):
        config.background_neighbor_radius = max(
            20.0, baseline["background_neighbor_radius"] * safe
        )
    if hasattr(config, "background_player_guard"):
        config.background_player_guard = max(
            20.0, baseline["background_player_guard"] * safe
        )
    if hasattr(config, "reacquire_distance"):
        config.reacquire_distance = max(30.0, baseline["reacquire_distance"] * safe)


def _apply_observer_geometry(observer, mode: str, cell_size: float, source: str) -> None:
    desired = max(8.0, min(160.0, float(cell_size)))
    previous = float(getattr(observer, "tile_size", 32.0) or 32.0)
    if abs(previous - desired) <= 0.05 and getattr(observer, "_kagelink_geometry_mode", None) == mode:
        return

    had_geometry = hasattr(observer, "_kagelink_geometry_mode")
    observer.tile_size = desired
    observer.grid_origin_x = float(getattr(observer, "grid_origin_x", 0.0)) % desired
    observer.grid_origin_y = float(getattr(observer, "grid_origin_y", 0.0)) % desired
    observer._grid_alignment_ready = False
    observer._kagelink_geometry_mode = mode
    observer._kagelink_geometry_source = source
    _scale_observer_config(observer.config, desired / 32.0)

    if had_geometry:
        try:
            observer.reset()
        except Exception:
            pass
        observer._grid_alignment_ready = False

    print(
        "DOJO_OBSERVER_GEOMETRY "
        f"mode={mode} cell_size={desired:.3f} source={source}"
    )


def _install_dynamic_observer_grid() -> None:
    from .grid_target_observer_v03d import TileCalibratedGridTargetObserver

    if bool(getattr(TileCalibratedGridTargetObserver, "_kagelink_dynamic_grid", False)):
        return

    original_process = TileCalibratedGridTargetObserver.process
    original_character_like = TileCalibratedGridTargetObserver._character_like

    def process(self, frame_bgr: np.ndarray, *, timestamp: float | None = None):
        desired = _desired_geometry()
        if desired is not None:
            mode, cell_size, source = desired
            _apply_observer_geometry(self, mode, cell_size, source)
        return original_process(self, frame_bgr, timestamp=timestamp)

    def character_like(self, track) -> bool:
        tile_size = max(8.0, float(getattr(self, "tile_size", 32.0) or 32.0))
        if tile_size >= 27.0:
            return original_character_like(self, track)
        _, _, width, height = track.bbox
        width = max(1.0, float(width))
        height = max(1.0, float(height))
        ratio = tile_size / 32.0
        aspect = height / width
        return (
            height >= max(7.0, 14.0 * ratio)
            and width <= max(18.0, tile_size * 1.80)
            and 0.50 <= aspect <= 4.8
            and track.shape_score >= max(0.14, 0.22 * ratio)
        )

    TileCalibratedGridTargetObserver.process = process
    TileCalibratedGridTargetObserver._character_like = character_like
    TileCalibratedGridTargetObserver._kagelink_dynamic_grid = True


def _install_dynamic_search_grid() -> None:
    from .post_combat_v03e import ObstacleAwarePostCombatRecoveryEngine

    if bool(getattr(ObstacleAwarePostCombatRecoveryEngine, "_kagelink_dynamic_search_grid", False)):
        return

    original_observe = ObstacleAwarePostCombatRecoveryEngine.observe_movement_frame

    def observe_movement_frame(self, frame_bgr, observer_state, *, now: float) -> None:
        desired = _desired_geometry()
        if desired is not None:
            mode, cell_size, source = desired
            x0, y0, x1, y1 = (int(value) for value in observer_state.arena_rect)
            width_cells = max(2, min(200, math.ceil(max(1, x1 - x0) / cell_size)))
            height_cells = max(2, min(200, math.ceil(max(1, y1 - y0) / cell_size)))
            pulses_per_cell = max(1, min(10, round(4.0 * cell_size / 32.0)))
            signature = (
                mode,
                round(float(cell_size), 3),
                width_cells,
                height_cells,
                pulses_per_cell,
                source,
            )
            if getattr(self, "_kagelink_search_grid_signature", None) != signature:
                search = getattr(self, "search", None)
                if search is not None:
                    search.pulses_per_cell = pulses_per_cell
                    search.arena_width_cells = width_cells
                    search.arena_height_cells = height_cells
                    search.max_radius = max(width_cells - 1, height_cells - 1)
                    search.reset()
                self._kagelink_search_grid_signature = signature
                print(
                    "DOJO_SEARCH_GRID_CALIBRATED "
                    f"mode={mode} cell_size={cell_size:.3f} "
                    f"arena_cells={width_cells}x{height_cells} "
                    f"pulses_per_cell={pulses_per_cell} source={source}"
                )
        return original_observe(self, frame_bgr, observer_state, now=now)

    ObstacleAwarePostCombatRecoveryEngine.observe_movement_frame = observe_movement_frame
    ObstacleAwarePostCombatRecoveryEngine._kagelink_dynamic_search_grid = True


def _replace_loaded_detector_aliases() -> None:
    replacement = BoundedResolutionIndependentDojoLeaderDetector
    previous = _ORIGINAL_RESOLUTION_DETECTOR
    _bridge.ResolutionIndependentDojoLeaderDetector = replacement

    aliases: Iterable[tuple[str, str]] = (
        ("pc_agent.kage_pilot.dojo_templates", "UserDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_templates_v35", "UserDojoLeaderDetector"),
        ("pc_agent.kage_pilot.post_combat_v03c", "PersistentDojoLeaderDetector"),
        ("pc_agent.kage_pilot.trainer_search_v03k", "PersistentDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_position_bridge", "UserDojoLeaderDetector"),
        (
            "pc_agent.kage_pilot.dojo_resolution_scope_compat_v351",
            "ResolutionIndependentDojoLeaderDetector",
        ),
    )
    for module_name, attribute in aliases:
        module = sys.modules.get(module_name)
        if module is None or not hasattr(module, attribute):
            continue
        current = getattr(module, attribute)
        if current is previous or current is _bridge.ResolutionIndependentDojoLeaderDetector:
            setattr(module, attribute, replacement)

    # The parent Trainer acquisition alias is the required authority even when the
    # scope-compat layer intentionally restored generic post-combat providers.
    trainer_module = sys.modules.get("pc_agent.kage_pilot.trainer_search_v03k")
    if trainer_module is not None:
        setattr(trainer_module, "PersistentDojoLeaderDetector", replacement)
    monitor_module = sys.modules.get("pc_agent.kage_pilot.dojo_position_bridge")
    if monitor_module is not None:
        setattr(monitor_module, "UserDojoLeaderDetector", replacement)
    scope_module = sys.modules.get("pc_agent.kage_pilot.dojo_resolution_scope_compat_v351")
    if scope_module is not None:
        setattr(scope_module, "ResolutionIndependentDojoLeaderDetector", replacement)


def install_resolution_runtime_fix() -> None:
    global _INSTALLED
    _replace_loaded_detector_aliases()
    _install_dynamic_observer_grid()
    _install_dynamic_search_grid()
    _INSTALLED = True


__all__ = [
    "BoundedResolutionIndependentDojoLeaderDetector",
    "install_resolution_runtime_fix",
]
