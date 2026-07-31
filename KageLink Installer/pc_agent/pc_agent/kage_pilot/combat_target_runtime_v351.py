from __future__ import annotations

from dataclasses import replace
import time
from typing import Any

from .combat_target_config_v351 import load_combat_target_config
from .combat_target_filter_v351 import (
    candidate_bbox,
    combat_body_rejection_reason,
    effect_rejection_reason,
)
from .combat_target_memory_v351 import PersistentCombatTargetMemory, Telemetry
from .combat_target_model_v351 import (
    CombatDecisionV351,
    CombatTargetSnapshot,
    CombatTargetState,
    RejectedCandidate,
)


_CARDINAL = {"LEFT", "RIGHT", "UP", "DOWN"}
_DIRECTION_KEYS = {
    "LEFT": "left",
    "RIGHT": "right",
    "UP": "up",
    "DOWN": "down",
}
_LAST_COMMAND_BY_TARGET: dict[int, str] = {}


def _decision_from_base(
    base: Any,
    snapshot: CombatTargetSnapshot,
    **overrides: object,
) -> CombatDecisionV351:
    values: dict[str, object] = {
        "mode": str(getattr(base, "mode", "ENGAGED_SEARCH")),
        "navigation": str(getattr(base, "navigation", "HOLD")),
        "face": str(getattr(base, "face", "-")),
        "base_r": bool(getattr(base, "base_r", True)),
        "h_opportunity": bool(getattr(base, "h_opportunity", False)),
        "target_id": getattr(base, "target_id", None),
        "grid_distance": getattr(base, "grid_distance", None),
        "reason": str(getattr(base, "reason", "")),
        "engagement_active": bool(getattr(base, "engagement_active", True)),
        "engagement_stable_seconds": float(
            getattr(base, "engagement_stable_seconds", 0.0) or 0.0
        ),
        "combat_target_id": snapshot.combat_target_id,
        "visual_track_id": snapshot.current_visual_track_id,
        "target_state": snapshot.target_state,
        "target_confidence": snapshot.confidence,
        "movement_mode": snapshot.movement_mode,
        "predicted_position": snapshot.predicted_position,
        "time_since_last_seen": snapshot.time_since_last_seen,
    }
    values.update(overrides)
    return CombatDecisionV351(**values)  # type: ignore[arg-type]


def current_combat_command(combat_target_id: int | None) -> str:
    if combat_target_id is None:
        return "-"
    return _LAST_COMMAND_BY_TARGET.get(int(combat_target_id), "-")


def install_combat_target_bridge(runtime: Any):
    """Install persistent identity behind a fail-closed physical authority boundary."""

    import kage_pilot_live_v03 as live_runtime

    if bool(getattr(live_runtime, "_kagelink_v351_combat_target_installed", False)):
        return live_runtime.ParticleSafeGridTargetObserver

    telemetry: Telemetry | None = getattr(runtime, "_telemetry", None)
    config = load_combat_target_config()
    BaseTracker = live_runtime.PersistentBackgroundWaterAwareEntityTracker
    BaseObserver = live_runtime.ParticleSafeGridTargetObserver
    BaseEngine = live_runtime.ShadowCombatDecisionEngine
    BasePlanner = live_runtime.LiveCombatControlPlanner

    class CombatFilteredTracker(BaseTracker):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.raw_candidate_count = 0
            self.filtered_candidate_count = 0
            self.rejected_candidates: tuple[RejectedCandidate, ...] = ()
            self._last_rejection_signature: tuple[
                tuple[str, tuple[int, int, int, int]], ...
            ] = ()
            self._last_rejection_event_at = -1e9

        def update(self, candidates, *, flow, player_center, now):
            raw = list(candidates)
            gray = getattr(self, "_frame_gray", None)
            frame_shape = tuple(gray.shape[:2]) if getattr(gray, "size", 0) else None
            filtered = []
            rejected: list[RejectedCandidate] = []
            for candidate in raw:
                reason = effect_rejection_reason(
                    candidate,
                    frame_shape=frame_shape,
                    flow=flow,
                    player_center=player_center,
                    config=config,
                )
                if reason is None:
                    filtered.append(candidate)
                else:
                    rejected.append(RejectedCandidate(candidate_bbox(candidate), reason))
            self.raw_candidate_count = len(raw)
            self.filtered_candidate_count = len(filtered)
            self.rejected_candidates = tuple(rejected)
            signature = tuple((item.reason, item.bbox) for item in rejected[:12])
            if signature and (
                signature != self._last_rejection_signature
                or float(now) - self._last_rejection_event_at >= 0.75
            ):
                self._last_rejection_signature = signature
                self._last_rejection_event_at = float(now)
                fields = {
                    "count": len(rejected),
                    "reasons": ",".join(sorted({item.reason for item in rejected})),
                    "raw_candidates": len(raw),
                    "filtered_candidates": len(filtered),
                }
                if telemetry is not None:
                    telemetry("DOJO_COMBAT_CANDIDATES_REJECTED", fields)
            result = super().update(
                filtered,
                flow=flow,
                player_center=player_center,
                now=now,
            )
            suppressed = int(
                getattr(
                    getattr(self, "background", None),
                    "suppressed_last_frame",
                    0,
                )
                or 0
            )
            self.filtered_candidate_count = max(0, len(filtered) - suppressed)
            return result

    base_apply_resync = getattr(BaseObserver, "_apply_resync_if_needed", None)

    class PersistentCombatTargetObserver(BaseObserver):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.combat_memory = PersistentCombatTargetMemory(config, telemetry=telemetry)
            self._combat_frame_index = 0
            self._combat_last_snapshot = self.combat_memory.snapshot(
                now=time.monotonic(),
                frame_index=0,
            )
            self._combat_soft_resyncs = 0
            self._last_body_rejection: tuple[int, str] | None = None
            self._last_body_rejection_at = -1e9

        @property
        def combat_target_id(self) -> int | None:
            return self.combat_memory.combat_target_id

        @property
        def combat_target_state(self) -> str:
            return self.combat_memory.state.value

        def combat_snapshot(self) -> CombatTargetSnapshot:
            return self._combat_last_snapshot

        def reset(self) -> None:
            super().reset()
            if hasattr(self, "combat_memory"):
                self.combat_memory.reset(preserve_sequence=True)
            self._combat_frame_index = 0

        def _apply_resync_if_needed(self) -> None:
            try:
                import kage_pilot_live_v03i_round as resync_runtime

                generation = int(getattr(resync_runtime._RESYNC, "generation", 0))
            except Exception:
                generation = int(getattr(self, "_resync_generation", 0))
            current_generation = int(getattr(self, "_resync_generation", generation))
            if current_generation == generation:
                return
            if (
                getattr(self, "combat_memory", None) is not None
                and self.combat_memory.active
            ):
                self._resync_generation = generation
                self._previous_gray = None
                self._grid_target_id = None
                self._locked_target_id = None
                self._last_metrics = {}
                self._active_cells = set()
                request_realign = getattr(self, "request_grid_realign", None)
                if callable(request_realign):
                    request_realign()
                self._combat_soft_resyncs += 1
                if telemetry is not None:
                    telemetry(
                        "DOJO_COMBAT_SOFT_RESYNC",
                        {
                            "generation": generation,
                            "combat_target_id": self.combat_memory.combat_target_id,
                            "preserved_tracker": "true",
                            "preserved_background": "true",
                        },
                    )
                return
            if callable(base_apply_resync):
                base_apply_resync(self)

        def _context_and_metrics(self, track: Any):
            track_id = int(getattr(track, "track_id", 0) or 0)
            return self.tracker.context_for(track_id), self.metrics_for(track_id)

        def combat_track_rejection_reason(
            self,
            track: Any,
            *,
            state: Any | None = None,
            for_acquire: bool = False,
        ) -> str | None:
            context, metrics = self._context_and_metrics(track)
            if metrics is None:
                return "BODY_NO_GRID_METRICS"
            frame_shape = None
            if state is not None:
                mask = getattr(state, "motion_mask", None)
                if getattr(mask, "size", 0):
                    frame_shape = tuple(mask.shape[:2])
            return combat_body_rejection_reason(
                track,
                context_state=str(getattr(context, "state", "") or ""),
                grid_distance=int(getattr(metrics, "grid_distance", 99)),
                player_center=(
                    tuple(float(value) for value in state.player_center)
                    if state is not None
                    else (0.0, 0.0)
                ),
                player_box_size=(
                    float(getattr(self.config, "player_box_width", 18.0) or 18.0),
                    float(getattr(self.config, "player_box_height", 38.0) or 38.0),
                ),
                tile_size=float(getattr(self, "tile_size", 32.0) or 32.0),
                frame_shape=frame_shape,
                for_acquire=for_acquire,
            )

        def _report_body_rejection(self, track: Any, reason: str, now: float) -> None:
            signature = (int(getattr(track, "track_id", 0) or 0), str(reason))
            if signature == self._last_body_rejection and now - self._last_body_rejection_at < 0.75:
                return
            self._last_body_rejection = signature
            self._last_body_rejection_at = now
            if telemetry is not None:
                telemetry(
                    "DOJO_COMBAT_BODY_REJECTED",
                    {
                        "visual_track_id": signature[0],
                        "reason": signature[1],
                        "bbox": candidate_bbox(track),
                    },
                )

        def process(self, frame_bgr, *, timestamp=None):
            state = super().process(frame_bgr, timestamp=timestamp)
            self._combat_frame_index += 1
            now = float(state.timestamp)
            tracks = tuple(getattr(state, "tracks", ()) or ())
            player_center = tuple(float(value) for value in state.player_center)
            memory = self.combat_memory
            chosen = None
            rebound_score = 0.0

            if memory.active:
                current = next(
                    (
                        track
                        for track in tracks
                        if int(getattr(track, "track_id", 0) or 0)
                        == memory.visual_track_id
                    ),
                    None,
                )
                if current is not None:
                    reason = self.combat_track_rejection_reason(
                        current,
                        state=state,
                        for_acquire=False,
                    )
                    if reason is None:
                        chosen = current
                    else:
                        self._report_body_rejection(current, reason, now)
                if chosen is None:
                    chosen, rebound_score = memory.choose_local_rebind(
                        tracks,
                        tracker=self.tracker,
                        observer=self,
                        player_center=player_center,
                    )
                if chosen is not None:
                    context, metrics = self._context_and_metrics(chosen)
                    memory.observe(
                        chosen,
                        context,
                        metrics,
                        player_center=player_center,
                        now=now,
                        frame_index=self._combat_frame_index,
                        rebound=(
                            int(getattr(chosen, "track_id", 0) or 0)
                            != memory.visual_track_id
                        ),
                        rebind_score=rebound_score,
                    )
                    state = replace(
                        state,
                        target_id=int(getattr(chosen, "track_id", 0) or 0),
                    )
                else:
                    flow = getattr(state, "global_flow", None)
                    memory.mark_missing(
                        now=now,
                        frame_index=self._combat_frame_index,
                        flow=(
                            float(getattr(flow, "dx", 0.0) or 0.0),
                            float(getattr(flow, "dy", 0.0) or 0.0),
                        ),
                    )
                    state = replace(state, target_id=None)
            else:
                base_target = state.target
                if base_target is not None:
                    context, metrics = self._context_and_metrics(base_target)
                    reason = self.combat_track_rejection_reason(
                        base_target,
                        state=state,
                        for_acquire=True,
                    )
                    if metrics is not None and reason is None:
                        if memory.combat_target_id is None or memory.propose_switch(
                            int(getattr(base_target, "track_id", 0) or 0)
                        ):
                            memory.acquire(
                                base_target,
                                context,
                                metrics,
                                player_center=player_center,
                                now=now,
                                frame_index=self._combat_frame_index,
                            )
                    else:
                        if reason is not None:
                            self._report_body_rejection(base_target, reason, now)
                        state = replace(state, target_id=None)

            self._combat_last_snapshot = memory.snapshot(
                now=now,
                frame_index=self._combat_frame_index,
            )
            return state

    class PersistentCombatDecisionEngine(BaseEngine):
        """Use current measured geometry; memory may hold identity but never chase."""

        def decide(
            self,
            state,
            observer,
            tracker,
            *,
            now: float,
            skills_allowed: bool = True,
        ):
            base = super().decide(
                state,
                observer,
                tracker,
                now=now,
                skills_allowed=skills_allowed,
            )
            snapshot = observer.combat_snapshot()
            base_face = str(getattr(base, "face", "-")).upper()
            memory_face = str(snapshot.last_contact_direction or "-").upper()
            face = base_face if base_face in _CARDINAL else memory_face
            navigation = str(getattr(base, "navigation", "HOLD"))
            mode = str(getattr(base, "mode", "ENGAGED_SEARCH"))
            reason = str(getattr(base, "reason", ""))
            target_present = state.target is not None
            distance = getattr(base, "grid_distance", None)

            if snapshot.active and not target_present:
                # The failed physical round walked beyond an already lost enemy because
                # memory authorized MOVE for 0.6-1.5 seconds. Missing/occluded identity
                # now holds R and translation at zero until a body is visible again.
                mode = "MEMORY_HOLD"
                navigation = "HOLD"
                reason = (
                    f"combat target #{snapshot.combat_target_id} temporarily absent; "
                    f"state={snapshot.target_state}; translation denied until visible body"
                )
            elif snapshot.active:
                visible_pursuit = (
                    snapshot.target_state == CombatTargetState.VISIBLE.value
                    and snapshot.time_since_last_seen <= 0.20
                    and distance is not None
                    and int(distance) >= 3
                )
                if snapshot.movement_mode == "MELEE_LOCK" or not visible_pursuit:
                    mode = "MELEE" if snapshot.movement_mode == "MELEE_LOCK" else "VISUAL_HOLD"
                    navigation = f"FACE_{face}" if face in _CARDINAL else "HOLD"
                # For a current VISIBLE distant target, preserve the base engine's
                # same-frame grid direction. Never replace it with stale memory facing.
                reason += (
                    f"; combat_target={snapshot.combat_target_id} "
                    f"visual_track={snapshot.current_visual_track_id} "
                    f"target_state={snapshot.target_state} "
                    f"movement={snapshot.movement_mode} "
                    f"mode={str(getattr(observer, 'target_mode', '-')).lower()}"
                )

            contact_skill = (
                target_present
                and snapshot.target_state == CombatTargetState.CONTACT.value
                and snapshot.movement_mode == "MELEE_LOCK"
            )
            return _decision_from_base(
                base,
                snapshot,
                mode=mode,
                navigation=navigation,
                face=(face if face in _CARDINAL else str(getattr(base, "face", "-"))),
                h_opportunity=bool(getattr(base, "h_opportunity", False)) and contact_skill,
                reason=reason,
                target_id=getattr(state, "target_id", None),
                visual_track_id=getattr(state, "target_id", None),
            )

    class StableCombatControlPlanner(BasePlanner):
        """Emit at most one conservative pursuit pulse per fresh visual interval."""

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._physical_next_move_at = -1e9
            self._last_safety_event_at = -1e9

        def _safety_event(self, event: str, decision, command, now: float) -> None:
            if telemetry is None or now - self._last_safety_event_at < 0.50:
                return
            self._last_safety_event_at = now
            telemetry(
                event,
                {
                    "combat_target_id": getattr(decision, "combat_target_id", None),
                    "visual_track_id": getattr(decision, "visual_track_id", None),
                    "target_state": getattr(decision, "target_state", "-"),
                    "grid_distance": getattr(decision, "grid_distance", None),
                    "face": getattr(decision, "face", "-"),
                    "move_pulse": getattr(command, "move_pulse", None),
                    "face_pulse": getattr(command, "face_pulse", None),
                },
            )

        def plan(
            self,
            decision,
            *,
            now: float,
            movement_allowed: bool = True,
            block_reason: str = "",
        ):
            proxy = decision
            logical_id = getattr(decision, "combat_target_id", None)
            if logical_id is not None:
                try:
                    proxy = replace(decision, target_id=int(logical_id))
                except Exception:
                    proxy = decision
            command = super().plan(
                proxy,
                now=now,
                movement_allowed=movement_allowed,
                block_reason=block_reason,
            )

            target_state = str(getattr(decision, "target_state", "") or "")
            movement_mode = str(getattr(decision, "movement_mode", "") or "")
            distance = getattr(decision, "grid_distance", None)
            distance_value = int(distance) if distance is not None else None
            face = str(getattr(decision, "face", "-") or "-").upper()
            expected_key = _DIRECTION_KEYS.get(face)
            fresh_visible_pursuit = (
                target_state == CombatTargetState.VISIBLE.value
                and movement_mode == "PURSUIT"
                and getattr(decision, "visual_track_id", None) is not None
                and float(getattr(decision, "time_since_last_seen", 99.0) or 99.0) <= 0.20
                and distance_value is not None
                and distance_value >= 3
            )

            if command.move_pulse is not None:
                deny_reason = None
                if not fresh_visible_pursuit:
                    deny_reason = "MOVE_WITHOUT_FRESH_VISIBLE_BODY"
                elif expected_key is None or command.move_pulse != expected_key:
                    deny_reason = "MOVE_DIRECTION_MISMATCH"
                elif float(now) < self._physical_next_move_at:
                    deny_reason = "MOVE_REOBSERVE_HOLD"
                if deny_reason is not None:
                    command = replace(
                        command,
                        move_pulse=None,
                        safety_state=deny_reason,
                        reason=str(command.reason) + f"; {deny_reason.lower()}",
                    )
                    self._safety_event("DOJO_COMBAT_MOVE_BLOCKED", decision, command, float(now))
                else:
                    self._physical_next_move_at = float(now) + 0.75
                    command = replace(
                        command,
                        safety_state="ONE_STEP_PURSUIT",
                        reason=str(command.reason) + "; one pulse then mandatory re-observation",
                    )

            if command.face_pulse is not None and (
                expected_key is None or command.face_pulse != expected_key
            ):
                command = replace(
                    command,
                    face_pulse=None,
                    h_fire=False,
                    safety_state="FACE_DIRECTION_MISMATCH",
                    reason=str(command.reason) + "; face mismatch blocked",
                )
                self._safety_event("DOJO_COMBAT_FACE_BLOCKED", decision, command, float(now))

            if movement_mode == "MELEE_LOCK" and command.move_pulse is not None:
                command = replace(
                    command,
                    move_pulse=None,
                    safety_state="MELEE_LOCK",
                    reason=str(command.reason) + "; translation denied in melee",
                )
            if target_state in {
                CombatTargetState.OCCLUDED_PREDICTED.value,
                CombatTargetState.LOCAL_REBIND.value,
                CombatTargetState.LOST.value,
            }:
                command = replace(command, move_pulse=None)
                if target_state == CombatTargetState.LOST.value:
                    command = replace(command, face_pulse=None, h_fire=False)

            if logical_id is not None:
                parts = []
                if command.held_keys:
                    parts.append("+".join(command.held_keys))
                if command.move_pulse:
                    parts.append(f"MOVE:{command.move_pulse}")
                if command.face_pulse:
                    parts.append(f"FACE:{command.face_pulse}")
                if command.h_fire:
                    parts.append("H")
                _LAST_COMMAND_BY_TARGET[int(logical_id)] = ",".join(parts) or "HOLD"
            return command

    live_runtime.PersistentBackgroundWaterAwareEntityTracker = CombatFilteredTracker
    live_runtime.ParticleSafeGridTargetObserver = PersistentCombatTargetObserver
    live_runtime.ShadowCombatDecisionEngine = PersistentCombatDecisionEngine
    live_runtime.LiveCombatControlPlanner = StableCombatControlPlanner
    live_runtime._kagelink_v351_combat_target_installed = True
    live_runtime._kagelink_v351_combat_target_config = config

    try:
        from .dojo_combat_vision_v351 import install_combat_vision_bridge

        install_combat_vision_bridge()
    except Exception as error:
        if telemetry is not None:
            telemetry(
                "DOJO_COMBAT_VISION_BRIDGE_FAILED",
                {"error": f"{type(error).__name__}:{error}"},
            )

    if telemetry is not None:
        telemetry(
            "DOJO_COMBAT_TARGET_BRIDGE_INSTALLED",
            {
                "contact_radius": f"{config.contact_radius:.1f}",
                "local_rebind_radius": f"{config.local_rebind_radius:.1f}",
                "hard_lost_timeout": f"{config.hard_lost_timeout:.2f}",
                "direction_confirm_frames": config.direction_confirm_frames,
                "target_switch_confirm_frames": config.target_switch_confirm_frames,
                "blind_pursuit": "disabled",
                "grid_anchor": "feet",
            },
        )
    return PersistentCombatTargetObserver


__all__ = ["current_combat_command", "install_combat_target_bridge"]
