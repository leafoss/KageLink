from __future__ import annotations

"""Physical fail-closed guard for floor/effect target regressions.

The canonical grid strategy remains the authority. This module closes three gaps
observed in the physical round-7 capture without restoring motion-first identity:

* large camera shifts and candidate explosions may not allocate new visual tracks;
* own-attack effects are quarantined before the strategy sees a clean body;
* contaminated contact may preserve an existing identity only briefly, only for the
  same tracker in the already confirmed cell, and never with movement/H authority.
"""

from dataclasses import replace
import math
from typing import Any, Callable

from .combat_strategy_v351 import (
    CombatPhase,
    CombatStrategyFrame,
    GridObservation,
    ObservationClass,
    PerceptionScope,
    size_similarity,
)
from .combat_strategy_runtime_v351 import (
    StrategyFilteredTrackerMixin,
    StrategyObserverMixin,
    _observation_for_track,
    _player_cell,
)
from .grid_focus_v2_strategy_v351 import GridFocusV2SpatialStrategy
from .grid_geometry_v351 import current_grid_geometry


Telemetry = Callable[[str, dict[str, object]], None]
_CONTACT_MEMORY_SECONDS = 0.70
_CONTACT_ACTIVITY_FRESH_SECONDS = 0.25
_CAMERA_TRACK_FREEZE_SECONDS = 0.35


def _cell_size(value: Any | None = None) -> float:
    geometry = current_grid_geometry()
    if geometry is not None:
        return float(geometry.cell_size)
    tile = float(getattr(value, "tile_size", 0.0) or 0.0)
    if tile in {32.0, 64.0}:
        return tile
    config = getattr(value, "config", None)
    player_height = float(getattr(config, "player_box_height", 38.0) or 38.0)
    return 64.0 if player_height >= 57.0 else 32.0


def _flow_components(flow: Any) -> tuple[float, float]:
    return (
        float(getattr(flow, "dx", 0.0) or 0.0),
        float(getattr(flow, "dy", 0.0) or 0.0),
    )


def _camera_shift_freeze_required(
    flow: Any,
    *,
    cell_size: float,
    candidate_count: int = 0,
    active_cells: int = 0,
    track_count: int = 0,
) -> bool:
    dx, dy = _flow_components(flow)
    magnitude = math.hypot(dx, dy)
    flow_threshold = max(8.0, min(12.0, float(cell_size) * 0.20))
    return bool(
        magnitude >= flow_threshold
        or int(candidate_count) >= 36
        or int(active_cells) >= 48
        or int(track_count) >= 32
    )


def _attack_cells(frame: CombatStrategyFrame) -> frozenset[tuple[int, int]]:
    attack = frame.attack_context
    if attack is None or not attack.active(frame.timestamp):
        return frozenset()
    return frozenset(set(attack.expected_cells) | {attack.origin_cell})


def _body_size_compatible(
    expected: tuple[float, float],
    observed: tuple[float, float],
) -> bool:
    expected_width = max(1e-6, float(expected[0]))
    expected_height = max(1e-6, float(expected[1]))
    observed_width = max(1e-6, float(observed[0]))
    observed_height = max(1e-6, float(observed[1]))
    width_ratio = min(expected_width, observed_width) / max(expected_width, observed_width)
    height_ratio = min(expected_height, observed_height) / max(expected_height, observed_height)
    return bool(
        width_ratio >= 0.55
        and height_ratio >= 0.55
        and size_similarity(expected, observed) >= 0.52
    )


def _contact_candidate_is_safe(
    *,
    frame: CombatStrategyFrame,
    target: Any,
    candidate: GridObservation,
    maximum_age: float = _CONTACT_MEMORY_SECONDS,
) -> bool:
    if frame.motion_burst or candidate.motion_burst:
        return False
    if candidate.track_id != int(target.clean_visual_track_id):
        return False
    if str(candidate.context_state).upper() != "OCCLUDED":
        return False
    if candidate.clean or candidate.multi_cell:
        return False
    if candidate.classification in {
        ObservationClass.CAMERA_OR_SCENE_MOTION.value,
        ObservationClass.MULTI_CELL_EFFECT.value,
        ObservationClass.TARGET_EFFECT_CONTAMINATED.value,
    }:
        return False
    if candidate.anchor_cell != tuple(target.confirmed_cell):
        return False
    if candidate.anchor_cell in _attack_cells(frame):
        return False
    if len(candidate.bbox_cells) > 2:
        return False
    clean_age = max(0.0, float(frame.timestamp) - float(target.last_clean_seen_at))
    if clean_age > float(maximum_age):
        return False
    if not _body_size_compatible(tuple(target.body_size), tuple(candidate.body_size)):
        return False
    return True


def _strict_clean_candidates(
    original: Callable[[Any, CombatStrategyFrame], list[GridObservation]],
    strategy: Any,
    frame: CombatStrategyFrame,
) -> list[GridObservation]:
    items = original(strategy, frame)
    tile = _cell_size()
    result: list[GridObservation] = []
    for item in items:
        width = max(1e-6, float(item.body_size[0]))
        height = max(1e-6, float(item.body_size[1]))
        aspect = height / width

        # Runtime observations use RAW pixels. Combat Lab fixtures intentionally use
        # normalized body dimensions; preserve those deterministic fixtures while
        # enforcing the physical pixel gate in the packaged BYOND runtime.
        physical_pixel_size = max(width, height) > 4.0
        if physical_pixel_size:
            if width < tile * 0.18 or height < tile * 0.50:
                continue
            if width > tile * 1.20 or height > tile * 1.40:
                continue
        if not 0.65 <= aspect <= 3.20:
            continue
        if len(item.bbox_cells) > 2:
            continue
        coverage = float(item.body_cell_coverage)
        if coverage > 0.0 and coverage < 0.22:
            continue
        result.append(item)
    return result


def _install_tracker_freeze(*, telemetry: Telemetry | None) -> None:
    original = StrategyFilteredTrackerMixin.update
    if bool(getattr(original, "_kagelink_physical_floor_guard", False)):
        return

    def guarded_update(self, candidates, *, flow, player_center, now):
        raw = list(candidates)
        tracks = getattr(self, "_tracks", {})
        track_count = len(tracks) if hasattr(tracks, "__len__") else 0
        freeze = _camera_shift_freeze_required(
            flow,
            cell_size=_cell_size(self),
            candidate_count=len(raw),
            track_count=track_count,
        )
        freeze_until = float(getattr(self, "_kagelink_camera_freeze_until", -1e9))
        if freeze:
            freeze_until = max(freeze_until, float(now) + _CAMERA_TRACK_FREEZE_SECONDS)
            self._kagelink_camera_freeze_until = freeze_until
        active = freeze or float(now) < freeze_until
        if active:
            dx, dy = _flow_components(flow)
            if telemetry is not None:
                last = float(getattr(self, "_kagelink_camera_freeze_telemetry_at", -1e9))
                if float(now) - last >= 0.50:
                    self._kagelink_camera_freeze_telemetry_at = float(now)
                    telemetry(
                        "DOJO_CAMERA_SHIFT_TRACK_FREEZE",
                        {
                            "flow_dx": f"{dx:.2f}",
                            "flow_dy": f"{dy:.2f}",
                            "raw_candidates": len(raw),
                            "existing_tracks": track_count,
                            "hold_seconds": _CAMERA_TRACK_FREEZE_SECONDS,
                            "action": "NO_NEW_TRACKS_PRESERVE_EXISTING",
                        },
                    )
            raw = []
        return original(
            self,
            raw,
            flow=flow,
            player_center=player_center,
            now=now,
        )

    guarded_update._kagelink_physical_floor_guard = True
    StrategyFilteredTrackerMixin.update = guarded_update


def _install_strategy_guards() -> None:
    strategy_type = GridFocusV2SpatialStrategy
    strategy_type._MAX_CONTACT_SUSPENSION_SECONDS = _CONTACT_MEMORY_SECONDS
    strategy_type._CONTACT_ACTIVITY_FRESH_SECONDS = _CONTACT_ACTIVITY_FRESH_SECONDS

    original_clean = strategy_type._clean_candidates
    if not bool(getattr(original_clean, "_kagelink_physical_floor_guard", False)):

        def clean_candidates(self, frame):
            return _strict_clean_candidates(original_clean, self, frame)

        clean_candidates._kagelink_physical_floor_guard = True
        strategy_type._clean_candidates = clean_candidates

    current_contact = strategy_type._same_track_contact_presence
    if not bool(getattr(current_contact, "_kagelink_physical_floor_guard", False)):

        def strict_same_track_contact_presence(self, frame):
            target = self._target
            if target is None:
                return False
            candidate = next(
                (
                    item
                    for item in frame.observations
                    if _contact_candidate_is_safe(
                        frame=frame,
                        target=target,
                        candidate=item,
                    )
                ),
                None,
            )
            if candidate is None:
                self._same_track_contact_started_at = -1e9
                return False
            if self._same_track_contact_started_at < -1e8:
                self._same_track_contact_started_at = frame.timestamp
            target.current_clean_visible = False
            target.last_any_activity_at = max(target.last_any_activity_at, frame.timestamp)
            target.contamination = "CONTACT_OCCLUDED"
            target.possible_presence_in_locked_cell = True
            self._scope = PerceptionScope.PREDICTED_CELL_FOCUS
            self._last_reason = (
                f"same tracker #{candidate.track_id} briefly preserved in confirmed cell; "
                "MOVE/H denied and clean memory frozen"
            )
            return True

        strict_same_track_contact_presence._kagelink_physical_floor_guard = True
        strategy_type._same_track_contact_presence = strict_same_track_contact_presence

    current_contaminated = strategy_type._contaminated_presence
    if not bool(getattr(current_contaminated, "_kagelink_physical_floor_guard", False)):

        def strict_contaminated_presence(self, frame):
            target = self._target
            if target is None or frame.motion_burst:
                return
            for item in frame.observations:
                if not _contact_candidate_is_safe(
                    frame=frame,
                    target=target,
                    candidate=item,
                ):
                    continue
                target.last_any_activity_at = max(
                    target.last_any_activity_at,
                    frame.timestamp,
                )
                target.contamination = "CONTACT_OCCLUDED"
                target.possible_presence_in_locked_cell = True
                self._last_reason = (
                    "brief same-track occlusion in confirmed cell; main identity unchanged"
                )
                return

        strict_contaminated_presence._kagelink_physical_floor_guard = True
        strategy_type._contaminated_presence = strict_contaminated_presence


def _install_observer_frame_guard(*, telemetry: Telemetry | None) -> None:
    current = StrategyObserverMixin.process
    if bool(getattr(current, "_kagelink_physical_floor_guard", False)):
        return

    def guarded_process(self, frame_bgr, *, timestamp=None):
        state = super(StrategyObserverMixin, self).process(
            frame_bgr,
            timestamp=timestamp,
        )
        self._combat_frame_index += 1
        player_cell = _player_cell(self, state)
        if self.combat_strategy._phase == CombatPhase.POST_COMBAT:
            tracker = getattr(self, "tracker", None)
            if tracker is not None and hasattr(tracker, "full_reset"):
                tracker.full_reset()
            frame = CombatStrategyFrame(
                frame_index=self._combat_frame_index,
                timestamp=float(state.timestamp),
                player_cell=player_cell,
                observations=(),
            )
            self._combat_last_snapshot = self.combat_strategy.update(frame)
            return replace(state, tracks=(), target_id=None)

        active_cells = len(tuple(getattr(self, "_active_cells", ()) or ()))
        tracks = tuple(getattr(state, "tracks", ()) or ())
        flow = getattr(state, "global_flow", None)
        tile = _cell_size(self)
        motion_burst = _camera_shift_freeze_required(
            flow,
            cell_size=tile,
            active_cells=active_cells,
            track_count=len(tracks),
        )
        dx, dy = _flow_components(flow)
        camera_shift = (
            max(-1, min(1, int(round(dx / max(1.0, tile))))),
            max(-1, min(1, int(round(dy / max(1.0, tile))))),
        )

        raw_observations = tuple(
            _observation_for_track(
                self,
                state,
                track,
                frame_index=self._combat_frame_index,
            )
            for track in tracks
        )
        attack = self._attack_visual_context
        attack_cells = (
            frozenset(set(attack.expected_cells) | {attack.origin_cell})
            if attack is not None and attack.active(float(state.timestamp))
            else frozenset()
        )
        observations: list[GridObservation] = []
        attack_quarantined = 0
        for item in raw_observations:
            if motion_burst:
                item = replace(
                    item,
                    body_like=False,
                    contaminated=True,
                    classification=ObservationClass.CAMERA_OR_SCENE_MOTION.value,
                    motion_burst=True,
                )
            elif item.anchor_cell in attack_cells:
                item = replace(
                    item,
                    body_like=False,
                    contaminated=True,
                    classification=ObservationClass.TARGET_EFFECT_CONTAMINATED.value,
                )
                attack_quarantined += 1
            observations.append(item)

        if telemetry is not None and motion_burst:
            last = float(getattr(self, "_kagelink_frame_freeze_telemetry_at", -1e9))
            if float(state.timestamp) - last >= 0.50:
                self._kagelink_frame_freeze_telemetry_at = float(state.timestamp)
                telemetry(
                    "DOJO_CAMERA_SHIFT_IDENTITY_FREEZE",
                    {
                        "flow_dx": f"{dx:.2f}",
                        "flow_dy": f"{dy:.2f}",
                        "active_cells": active_cells,
                        "tracks": len(tracks),
                        "action": "HOLD_NO_REBIND_NO_MOVE_NO_H",
                    },
                )
        if telemetry is not None and attack_quarantined:
            last = float(getattr(self, "_kagelink_attack_quarantine_telemetry_at", -1e9))
            if float(state.timestamp) - last >= 0.50:
                self._kagelink_attack_quarantine_telemetry_at = float(state.timestamp)
                telemetry(
                    "DOJO_ATTACK_EFFECT_QUARANTINE",
                    {
                        "attack_id": int(attack.attack_id) if attack is not None else -1,
                        "tracks": attack_quarantined,
                        "cells": sorted(attack_cells),
                        "action": "NO_TARGET_NO_REBIND_NO_TIMEOUT_RENEWAL",
                    },
                )

        self._last_strategy_observations = tuple(observations)
        frame = CombatStrategyFrame(
            frame_index=self._combat_frame_index,
            timestamp=float(state.timestamp),
            player_cell=player_cell,
            observations=tuple(observations),
            attack_context=attack,
            camera_shift=camera_shift,
            motion_burst=motion_burst,
        )
        snapshot = self.combat_strategy.update(frame)
        self._combat_last_snapshot = snapshot
        selected_id = snapshot.current_visual_track_id
        selected = next(
            (
                item
                for item in observations
                if item.track_id == selected_id and item.clean
            ),
            None,
        )
        authoritative_id = selected.track_id if selected is not None else None
        self._grid_target_id = authoritative_id
        self._locked_target_id = authoritative_id
        return replace(state, target_id=authoritative_id)

    guarded_process._kagelink_physical_floor_guard = True
    StrategyObserverMixin.process = guarded_process


def install_physical_floor_guard(runtime: Any) -> None:
    """Install the round-7 floor/effect fail-closed corrections."""

    telemetry: Telemetry | None = getattr(runtime, "_telemetry", None)
    _install_tracker_freeze(telemetry=telemetry)
    _install_strategy_guards()
    _install_observer_frame_guard(telemetry=telemetry)
    if telemetry is not None:
        telemetry(
            "DOJO_PHYSICAL_FLOOR_GUARD_INSTALLED",
            {
                "strategy_required": "grid_focus_v2",
                "contact_memory_seconds": _CONTACT_MEMORY_SECONDS,
                "contact_activity_fresh_seconds": _CONTACT_ACTIVITY_FRESH_SECONDS,
                "camera_track_freeze_seconds": _CAMERA_TRACK_FREEZE_SECONDS,
                "attack_origin_quarantined": True,
                "occluded_new_target": False,
                "contaminated_move": False,
                "contaminated_h": False,
            },
        )


__all__ = [
    "_body_size_compatible",
    "_camera_shift_freeze_required",
    "_contact_candidate_is_safe",
    "install_physical_floor_guard",
]
