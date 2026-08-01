from __future__ import annotations

import math
import sys

from .dojo_raw_trainer_v351 import (
    RawDojoLeaderDetector,
    install_raw_trainer_pipeline,
)


_CONFIG_BASELINES: dict[int, dict[str, float]] = {}
_INSTALLED = False
# Compatibility export. The implementation is exact RAW matching, not bounded
# scaled matching.
BoundedResolutionIndependentDojoLeaderDetector = RawDojoLeaderDetector


def _desired_geometry() -> tuple[str, float, str] | None:
    from .dojo_resolution_bridge_v351 import read_dojo_geometry

    geometry = read_dojo_geometry()
    if geometry is None:
        return None
    return (
        geometry.template_mode,
        float(geometry.effective_tile_size),
        "confirmed-raw-template",
    )


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
            "background_neighbor_radius": float(getattr(config, "background_neighbor_radius", 58.0)),
            "background_player_guard": float(getattr(config, "background_player_guard", 78.0)),
            "reacquire_distance": float(getattr(config, "reacquire_distance", 180.0)),
        }
        _CONFIG_BASELINES[key] = baseline

    safe = 1.0 if float(ratio) < 1.5 else 2.0
    area_scale = safe * safe
    config.min_candidate_area = max(12.0, baseline["min_candidate_area"] * area_scale)
    config.max_candidate_area = max(450.0, baseline["max_candidate_area"] * area_scale)
    config.min_candidate_width = max(3, round(baseline["min_candidate_width"] * safe))
    config.min_candidate_height = max(5, round(baseline["min_candidate_height"] * safe))
    config.max_candidate_width = max(36, round(baseline["max_candidate_width"] * safe))
    config.max_candidate_height = max(48, round(baseline["max_candidate_height"] * safe))
    if hasattr(config, "background_cell_size"):
        config.background_cell_size = baseline["background_cell_size"] * safe
    if hasattr(config, "background_neighbor_radius"):
        config.background_neighbor_radius = baseline["background_neighbor_radius"] * safe
    if hasattr(config, "background_player_guard"):
        config.background_player_guard = baseline["background_player_guard"] * safe
    if hasattr(config, "reacquire_distance"):
        config.reacquire_distance = baseline["reacquire_distance"] * safe


def _apply_observer_geometry(observer, mode: str, cell_size: float, source: str) -> None:
    desired = float(cell_size)
    if desired not in {32.0, 64.0}:
        return
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
        f"mode={mode} cell_size={desired:.3f} source={source} raw=true"
    )


def _install_dynamic_observer_grid() -> None:
    from .grid_target_observer_v03d import TileCalibratedGridTargetObserver

    if bool(getattr(TileCalibratedGridTargetObserver, "_kagelink_dynamic_grid", False)):
        return
    original_process = TileCalibratedGridTargetObserver.process
    original_character_like = TileCalibratedGridTargetObserver._character_like

    def process(self, frame_bgr, *, timestamp=None):
        desired = _desired_geometry()
        if desired is not None:
            _apply_observer_geometry(self, *desired)
        return original_process(self, frame_bgr, timestamp=timestamp)

    def character_like(self, track) -> bool:
        tile_size = float(getattr(self, "tile_size", 32.0) or 32.0)
        if tile_size <= 32.0:
            return original_character_like(self, track)
        _, _, width, height = track.bbox
        width = max(1.0, float(width))
        height = max(1.0, float(height))
        aspect = height / width
        return (
            height >= 28.0
            and width <= 115.0
            and 0.50 <= aspect <= 4.8
            and track.shape_score >= 0.22
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
            pulses_per_cell = 4 if cell_size == 32.0 else 8
            signature = (
                mode,
                cell_size,
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
                    f"pulses_per_cell={pulses_per_cell} source={source} raw=true"
                )
        return original_observe(self, frame_bgr, observer_state, now=now)

    ObstacleAwarePostCombatRecoveryEngine.observe_movement_frame = observe_movement_frame
    ObstacleAwarePostCombatRecoveryEngine._kagelink_dynamic_search_grid = True


def _replace_loaded_detector_aliases() -> None:
    aliases = (
        ("pc_agent.kage_pilot.dojo_templates", "UserDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_templates_v35", "UserDojoLeaderDetector"),
        ("pc_agent.kage_pilot.trainer_search_v03k", "PersistentDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_position_bridge", "UserDojoLeaderDetector"),
        ("pc_agent.kage_pilot.dojo_resolution_scope_compat_v351", "ResolutionIndependentDojoLeaderDetector"),
    )
    for module_name, attribute in aliases:
        module = sys.modules.get(module_name)
        if module is not None:
            setattr(module, attribute, RawDojoLeaderDetector)


def install_resolution_runtime_fix() -> None:
    global _INSTALLED
    _replace_loaded_detector_aliases()
    _install_dynamic_observer_grid()
    _install_dynamic_search_grid()
    install_raw_trainer_pipeline()
    _INSTALLED = True


__all__ = [
    "BoundedResolutionIndependentDojoLeaderDetector",
    "install_resolution_runtime_fix",
]
