from __future__ import annotations

import math
from collections import deque
from dataclasses import is_dataclass, replace
from types import SimpleNamespace
from typing import Any, Iterable

from .domain import GridCell
from .hostility_gate import EntityState, HostilityState
from .occupancy_model import DiffSource, OccupancyCluster, PR26ControlMode


_TRACKING_INSTALLED = False
_PHYSICAL_INSTALLED = False
_SEARCH_RADIUS_CELLS = 3
_NEAR_BODY_VOTES = 2
_NEAR_CONTACT_VOTES = 2


def cluster_distance_cells(
    cluster_or_cells: OccupancyCluster | Iterable[GridCell],
    player_cell: GridCell,
) -> int:
    """Return the minimum Chebyshev distance from the player to a cluster."""

    cells = getattr(cluster_or_cells, "cells", cluster_or_cells)
    values = tuple(cells)
    if not values:
        return 1_000_000
    return min(player_cell.chebyshev_distance(cell) for cell in values)


def within_player_search_radius(
    cluster_or_cells: OccupancyCluster | Iterable[GridCell],
    player_cell: GridCell,
    *,
    maximum: int = _SEARCH_RADIUS_CELLS,
) -> bool:
    """Only clusters at D<=3 may participate in initial enemy acquisition."""

    return cluster_distance_cells(cluster_or_cells, player_cell) <= int(maximum)


def near_vertical_body_evidence(
    cluster: OccupancyCluster,
    player_cell: GridCell,
) -> bool:
    """Strict visual body evidence for a nearby enemy when the raw tracker is absent.

    The PR26.7 physical log exposed the real opponent as one exact-baseline
    component around 25x44 px at 59 px from the player. The old rule rejected it
    solely because raw_ids was empty. This rule accepts only a compact vertical
    component inside D<=3; wide fields and distant clusters remain ineligible.
    """

    if not within_player_search_radius(cluster, player_cell):
        return False
    _, _, width, height = (int(value) for value in cluster.bbox)
    exact = any(
        getattr(item, "diff_source", None) is DiffSource.EXACT_CELL_BASELINE
        or bool(getattr(item, "reference_authoritative", False))
        for item in cluster.cell_observations
    )
    return bool(
        exact
        and 1 <= len(cluster.cells) <= 2
        and 10 <= width <= 72
        and 28 <= height <= 96
        and height >= width * 1.20
        and 0.07 <= float(cluster.true_changed_ratio) <= 0.55
        and float(cluster.occupancy_score) >= 0.55
        and int(cluster.largest_blob_area) >= 180
    )


def _wide_non_humanoid(cluster: OccupancyCluster) -> bool:
    _, _, width, height = (int(value) for value in cluster.bbox)
    aspect = float(width) / float(max(1, height))
    return bool(width >= 96 and height <= 72 and aspect >= 1.55)


def _copy_decision(decision: Any, **updates: Any) -> Any:
    allowed = {name: value for name, value in updates.items() if hasattr(decision, name)}
    if is_dataclass(decision):
        return replace(decision, **allowed)
    values = dict(vars(decision)) if hasattr(decision, "__dict__") else {}
    values.update(allowed)
    return SimpleNamespace(**values)


def install_near_enemy_focus_tracking() -> None:
    """Install PR26.8 local D<=3 enemy acquisition and pre-combat orientation."""

    global _TRACKING_INSTALLED
    if _TRACKING_INSTALLED:
        return

    from . import runtime_camera_compensation as camera_module
    from .occupancy_tracking import PR26OccupancyTracker

    original_artifact_reason = camera_module.proportional_artifact_reason

    def local_artifact_reason(cluster, **kwargs):
        reason = original_artifact_reason(cluster, **kwargs)
        if reason is not None:
            return reason
        if _wide_non_humanoid(cluster):
            return "WIDE_NON_HUMANOID_FIELD"
        return None

    camera_module.proportional_artifact_reason = local_artifact_reason

    original_associate = PR26OccupancyTracker._associate

    def radius_limited_associate(
        self,
        clusters,
        now,
        player_center,
        player_cell,
    ):
        self._pr26_current_player_cell = player_cell
        self._pr26_current_player_center = player_center
        locked_tracks = tuple(
            track for track in self._tracks.values() if bool(track.combat_lock)
        )
        accepted = []
        rejected = list(getattr(self.map, "last_rejected_clusters", ()))
        seen = getattr(self, "_pr26_seen_radius_rejections", set())

        for cluster in clusters:
            distance = cluster_distance_cells(cluster, player_cell)
            locked_continuity = any(
                track.foot_cell.chebyshev_distance(cluster.foot_cell) <= 2
                for track in locked_tracks
            )
            if distance <= _SEARCH_RADIUS_CELLS or locked_continuity:
                accepted.append(cluster)
                continue
            rejected.append(
                {
                    "reason": "OUTSIDE_PLAYER_RADIUS_D3",
                    "cells": tuple(
                        sorted(cluster.cells, key=lambda cell: (cell.y, cell.x))
                    ),
                    "bbox": cluster.bbox,
                    "distance_cells": distance,
                }
            )
            key = (tuple(sorted(cluster.cells)), int(distance))
            if key not in seen:
                seen.add(key)
                self._emit(
                    "PR26_CLUSTER_RANGE_REJECTED "
                    f"local_id={cluster.local_id} D={distance} max_D=3 "
                    f"cells={self._cells_text(cluster.cells)} bbox={cluster.bbox}"
                )

        self._pr26_seen_radius_rejections = seen
        self.map.last_rejected_clusters = tuple(rejected)
        self.last_clusters = tuple(accepted)
        self.map.last_clusters = self.last_clusters

        # A stale, unconfirmed track outside the local search area cannot retain
        # attention or compete with the nearby body. A confirmed combat target
        # may continue through the normal continuity path after knockback.
        metadata = getattr(self, "_pr26_hardening_meta", {})
        for track_id, track in tuple(self._tracks.items()):
            if track.combat_lock:
                continue
            if cluster_distance_cells(track.cells, player_cell) <= _SEARCH_RADIUS_CELLS:
                continue
            self._tracks.pop(track_id, None)
            metadata.pop(track_id, None)
            getattr(self, "_pr26_near_body_votes", {}).pop(track_id, None)
            getattr(self, "_pr26_visual_contact_votes", {}).pop(track_id, None)
            if getattr(self, "_pr26_selected_track_id", None) == track_id:
                self._pr26_selected_track_id = None
            self._emit(
                f"PR26_TRACK_RANGE_EXPIRED id={track_id} max_D=3 "
                f"cells={self._cells_text(track.cells)}"
            )

        return original_associate(
            self,
            tuple(accepted),
            now,
            player_center,
            player_cell,
        )

    PR26OccupancyTracker._associate = radius_limited_associate

    original_update = PR26OccupancyTracker._update_track

    def near_body_update(self, track, cluster, now, player_center, player_cell):
        original_update(self, track, cluster, now, player_center, player_cell)
        body_votes_by_id = getattr(self, "_pr26_near_body_votes", None)
        if body_votes_by_id is None:
            body_votes_by_id = {}
            self._pr26_near_body_votes = body_votes_by_id
        body_votes = body_votes_by_id.setdefault(track.track_id, deque(maxlen=3))
        body_now = near_vertical_body_evidence(cluster, player_cell)
        body_votes.append(body_now)

        # Replace this frame's negative raw/motion vote with strict local visual
        # body evidence instead of appending a second vote for the same frame.
        if body_now and track.entity_votes:
            track.entity_votes[-1] = True
        metadata = getattr(self, "_pr26_hardening_meta", {})
        meta = metadata.get(track.track_id)
        if body_now and meta is not None and getattr(meta, "entity_votes", None):
            meta.entity_votes[-1] = True

        confirmed_now = sum(body_votes) >= _NEAR_BODY_VOTES
        if confirmed_now:
            first_confirmation = track.entity_state is not EntityState.ENTITY_CONFIRMED
            track.entity_state = EntityState.ENTITY_CONFIRMED
            track.attention_lock = True
            grid_distance = cluster_distance_cells(cluster, player_cell)
            pixel_distance = math.dist(player_center, cluster.foot_point)
            if meta is not None:
                meta.quality = max(
                    float(getattr(meta, "quality", 0.0)),
                    2.25
                    + float(cluster.occupancy_score)
                    + max(0.0, (_SEARCH_RADIUS_CELLS - grid_distance) * 0.18),
                )
            if first_confirmation:
                self._emit(
                    f"PR26_NEAR_ENTITY_CONFIRMED id={track.track_id} D={grid_distance} "
                    f"pixel_distance={pixel_distance:.1f} bbox={cluster.bbox[2]}x{cluster.bbox[3]} "
                    f"votes={sum(body_votes)}/3 raw_ids={sorted(cluster.raw_track_ids)} "
                    "source=EXACT_VERTICAL_BODY"
                )

        contact_votes_by_id = getattr(self, "_pr26_visual_contact_votes", None)
        if contact_votes_by_id is None:
            contact_votes_by_id = {}
            self._pr26_visual_contact_votes = contact_votes_by_id
        contact_votes = contact_votes_by_id.setdefault(track.track_id, deque(maxlen=3))
        grid_distance = cluster_distance_cells(cluster, player_cell)
        pixel_distance = math.dist(player_center, cluster.foot_point)
        contact_now = bool(
            confirmed_now
            and body_now
            and (
                grid_distance <= 1
                or pixel_distance <= float(self.config.contact_distance_px)
            )
        )
        contact_votes.append(contact_now)

    PR26OccupancyTracker._update_track = near_body_update

    original_active = PR26OccupancyTracker._active

    def near_contact_active(self):
        selected = original_active(self)
        if selected is None:
            return None
        votes = getattr(self, "_pr26_visual_contact_votes", {}).get(
            selected.track_id,
            (),
        )
        if sum(votes) >= _NEAR_CONTACT_VOTES and not selected.combat_lock:
            selected.hostility_state = HostilityState.HOSTILE_CONFIRMED
            selected.combat_lock = True
            selected.reason = (
                "selected nearby exact-baseline vertical body sustained visual "
                "contact in 2-of-3 frames"
            )
            self._emit(
                f"PR26_NEAR_CONTACT_HOSTILITY id={selected.track_id} "
                f"votes={sum(votes)}/3 raw_ids={sorted(selected.raw_track_ids)} "
                "source=EXACT_VERTICAL_BODY"
            )
            self._emit(
                f"PR26_COMBAT_LOCK id={selected.track_id} active=True "
                "reason=NEAR_VERTICAL_CONTACT_2_OF_3",
                "COMBAT_LOCK_CHANGED",
            )
        return selected

    PR26OccupancyTracker._active = near_contact_active

    original_filter = PR26OccupancyTracker.filter_candidates

    def precombat_orientation_filter(self, *args, **kwargs):
        result = original_filter(self, *args, **kwargs)
        if result or self.mode is not PR26ControlMode.FULL_COMBAT:
            return result
        if not bool(getattr(self.map, "camera_alignment_authoritative", False)):
            return ()
        selected_id = getattr(self, "_pr26_selected_track_id", None)
        selected = self._tracks.get(selected_id) if selected_id is not None else None
        player_cell = getattr(self, "_pr26_current_player_cell", None)
        state = kwargs.get("state")
        if (
            selected is None
            or player_cell is None
            or state is None
            or selected.ambiguous
            or not selected.visible
            or not selected.face_only_lock
            or selected.entity_state is not EntityState.ENTITY_CONFIRMED
            or not within_player_search_radius(selected.cells, player_cell)
        ):
            return ()
        player = (
            float(state.player_center[0]),
            float(state.player_center[1]),
        )
        marker = (selected.track_id, self._face(player, selected.foot_point))
        if getattr(self, "_pr26_last_precombat_orientation", None) != marker:
            self._pr26_last_precombat_orientation = marker
            self._emit(
                f"PR26_PRECOMBAT_ORIENTATION id={selected.track_id} "
                f"direction={marker[1] or 'HOLD'} D="
                f"{cluster_distance_cells(selected.cells, player_cell)} "
                "authority=TURN_ONLY chase=BLOCKED H=BLOCKED"
            )
        return (self._candidate(selected, player),)

    PR26OccupancyTracker.filter_candidates = precombat_orientation_filter

    _TRACKING_INSTALLED = True
    print(
        "PR26.8 NEAR ENEMY FOCUS: acquisition limited to D<=3; 128x64 wide fields "
        "rejected; exact vertical nearby body can orient without raw_id; combat still "
        "requires selected 2-of-3 contact or autonomous approach"
    )


def install_near_enemy_focus_physical_gate() -> None:
    """Allow pre-lock turning in FULL_COMBAT while blocking chase and H."""

    global _PHYSICAL_INSTALLED
    if _PHYSICAL_INSTALLED:
        return

    from . import live_bridge as live_module
    from .runtime_tile_perception import current_hostility_gate

    CurrentPhysical = live_module.PhysicalCombatInput

    class NearEnemyFocusPhysicalInput(CurrentPhysical):
        def execute(self, decision, *, confirm_aim=None):
            mode = PR26ControlMode.from_environment()
            if mode is not PR26ControlMode.FULL_COMBAT:
                return super().execute(decision, confirm_aim=confirm_aim)

            gate = current_hostility_gate()
            snapshot = getattr(gate, "last_snapshot", None) if gate is not None else None
            if snapshot is None or bool(getattr(snapshot, "combat_lock", False)):
                return super().execute(decision, confirm_aim=confirm_aim)

            face_only = bool(getattr(snapshot, "face_only_lock", False))
            turn = getattr(decision, "turn_direction", None)
            r_authorized = bool(getattr(decision, "r_authorized", False))
            if face_only and turn and not r_authorized:
                self.controller.repeat_keys = set()
                self.controller.release_all()
                actions = tuple(
                    super().execute(decision, confirm_aim=confirm_aim)
                )
                return actions + ("PR26_D3_PRECOMBAT_TURN_ONLY",)

            safe = _copy_decision(
                decision,
                move=None,
                move_pulse_profile=None,
                move_pulse_ms=None,
                press_h=False,
                h_pulse_ms=None,
                h_authorized=False,
                h_cancel_reason="PR26_D3_WAITING_FOR_COMBAT_LOCK",
            )
            actions = tuple(super().execute(safe, confirm_aim=confirm_aim))
            return actions + ("PR26_D3_PRECOMBAT_CHASE_H_BLOCKED",)

    live_module.PhysicalCombatInput = NearEnemyFocusPhysicalInput
    _PHYSICAL_INSTALLED = True
    print(
        "PR26.8 PHYSICAL GATE: FULL_COMBAT may turn toward a selected D<=3 body "
        "before COMBAT_LOCK; chase and H remain blocked"
    )


__all__ = [
    "cluster_distance_cells",
    "install_near_enemy_focus_physical_gate",
    "install_near_enemy_focus_tracking",
    "near_vertical_body_evidence",
    "within_player_search_radius",
]
