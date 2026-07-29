from __future__ import annotations

from dataclasses import replace
import math

import kage_pilot_live_v03 as live_v03
import kage_pilot_live_v03i_round as round_v03i  # applies validated v0.3i patches first

from pc_agent.kage_pilot.post_combat_v03 import PostCombatDecision


_DIRECTION_KEYS = {
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
}

_PREVIOUS_PLANNER = live_v03.LiveCombatControlPlanner


class SelfOcclusionFastChakraRecoveryEngine(round_v03i.FastChakraVisualRecoveryEngine):
    """Step sideways once when Leafos likely hides an adjacent trainer sprite.

    The real-game failure showed this sequence: a current visual reached d<=1, Leafos stood
    directly below the trainer, template matching fell back to adjacent memory and the safety gate
    correctly refused to tap V. General reacquisition then risked starting toward the trainer.

    This layer keeps memory unable to authorize V. It only replaces the first bounded visual-search
    pulse with one perpendicular escape when the last visual is recent and the remembered trainer
    remains adjacent. Afterwards every key is released while current visual confirmation is retried.
    """

    def __init__(
        self,
        *args,
        self_occlusion_visual_recency_seconds: float = 3.0,
        self_occlusion_settle_seconds: float = 0.65,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.self_occlusion_visual_recency_seconds = max(
            1.0,
            min(8.0, float(self_occlusion_visual_recency_seconds)),
        )
        self.self_occlusion_settle_seconds = max(
            0.25,
            min(2.0, float(self_occlusion_settle_seconds)),
        )
        self._self_occlusion_escape_sent = False
        self._self_occlusion_wait_until = -1e9
        self._self_occlusion_direction: str | None = None

    def begin_post_combat(self) -> None:
        super().begin_post_combat()
        self._self_occlusion_escape_sent = False
        self._self_occlusion_wait_until = -1e9
        self._self_occlusion_direction = None

    @staticmethod
    def _player_full(observer_state) -> tuple[float, float]:
        x0, y0, _, _ = observer_state.arena_rect
        return (
            float(x0) + float(observer_state.player_center[0]),
            float(y0) + float(observer_state.player_center[1]),
        )

    @staticmethod
    def _preferred_perpendicular_directions(
        observer_state,
        trainer_foot: tuple[float, float],
    ) -> tuple[str, str]:
        """Choose the axis perpendicular to the trainer vector and prefer arena interior room."""

        player_x, player_y = SelfOcclusionFastChakraRecoveryEngine._player_full(observer_state)
        trainer_x, trainer_y = float(trainer_foot[0]), float(trainer_foot[1])
        dx = trainer_x - player_x
        dy = trainer_y - player_y
        x0, y0, x1, y1 = (float(value) for value in observer_state.arena_rect)

        # Trainer above/below: move laterally. Trainer left/right: move vertically. This explicitly
        # prevents the screenshot case (Leafos directly below) from producing an UP pulse.
        if abs(dy) >= abs(dx):
            room_left = max(0.0, player_x - x0)
            room_right = max(0.0, x1 - player_x)
            return ("right", "left") if room_right >= room_left else ("left", "right")

        room_up = max(0.0, player_y - y0)
        room_down = max(0.0, y1 - player_y)
        return ("down", "up") if room_down >= room_up else ("up", "down")

    def _recent_visual_match(self, *, now: float):
        detector = self.leader_detector
        match = getattr(detector, "_last_visual", None)
        seen_at = float(getattr(detector, "_last_visual_at", -1e9) or -1e9)
        if match is None:
            return None
        if float(now) - seen_at > self.self_occlusion_visual_recency_seconds:
            return None
        return match

    def _safe_self_occlusion_direction(self, observer_state, visual_match, *, now: float) -> str | None:
        candidates = self._preferred_perpendicular_directions(
            observer_state,
            tuple(visual_match.foot),
        )
        is_blocked = getattr(self, "_is_blocked", None)
        for candidate in candidates:
            if callable(is_blocked) and is_blocked(candidate, now=float(now)):
                continue
            return candidate
        return None

    @staticmethod
    def _is_adjacent_reacquire(decision) -> bool:
        distance = getattr(decision, "leader_distance", None)
        return (
            str(getattr(decision, "state", ""))
            in {"REACQUIRE_VISUAL_WAIT", "REACQUIRE_LEADER_VISUAL"}
            and distance is not None
            and int(distance) <= 1
            and not bool(getattr(decision, "tap_v", False))
        )

    def step(self, frame_bgr, observer_state, observer, *, now: float):
        now = float(now)
        decision = super().step(
            frame_bgr,
            observer_state,
            observer,
            now=now,
        )

        # A current visual or meditation transition cancels the post-pulse settle immediately.
        if decision.state not in {"REACQUIRE_VISUAL_WAIT", "REACQUIRE_LEADER_VISUAL"}:
            self._self_occlusion_wait_until = -1e9
            return decision

        if not self._is_adjacent_reacquire(decision):
            return decision

        if self._self_occlusion_escape_sent:
            if now < self._self_occlusion_wait_until:
                return PostCombatDecision(
                    state="SELF_OCCLUSION_WAIT",
                    leader_score=decision.leader_score,
                    leader_distance=decision.leader_distance,
                    reason=(
                        f"waiting after one {self._self_occlusion_direction or '-'} escape pulse; "
                        "V remains blocked until current visual / "
                        "aguardar apos um pulso de desoclusao; V bloqueado ate visao atual"
                    ),
                )
            return decision

        visual_match = self._recent_visual_match(now=now)
        if visual_match is None:
            return decision

        direction = self._safe_self_occlusion_direction(
            observer_state,
            visual_match,
            now=now,
        )
        if direction is None:
            return decision

        self._self_occlusion_escape_sent = True
        self._self_occlusion_direction = direction
        self._self_occlusion_wait_until = now + self.self_occlusion_settle_seconds
        return PostCombatDecision(
            state="SELF_OCCLUSION_ESCAPE",
            move_pulse=direction,
            tap_v=False,
            leader_score=decision.leader_score,
            leader_distance=decision.leader_distance,
            reason=(
                f"POSSIBLE_SELF_OCCLUSION: recent adjacent trainer visual hidden by player; "
                f"one perpendicular {direction} pulse then revalidate / "
                f"POSSIVEL_OCLUSAO_PELO_JOGADOR: um pulso perpendicular {direction} e revalidar"
            ),
        )


class BurstSafeMeleeFacingPlanner(_PREVIOUS_PLANNER):
    """Allow one visual melee facing correction while MotionBurstGuard blocks other actions.

    Real Dojo validation showed a long particle/burst hold where the combat decision had already
    changed from FACE_UP to FACE_DOWN, but the guard vetoed every directional pulse. R therefore
    remained active while the character physically faced away from an adjacent opponent.

    This exception is deliberately narrow:
    - only MELEE with grid distance <= 1;
    - only current visual authority (VISIBLE, OCCLUDED or CONTACT_REBIND), never CONTACT_MEMORY;
    - two stable decisions for the same target/direction;
    - at most one correction for that target/direction during the same uninterrupted burst hold;
    - no movement command and no H authority are restored;
    - H_SETTLE_HOLD and MAP_SAVE_RESYNC remain absolute holds.
    """

    def __init__(
        self,
        *args,
        burst_face_confirm_frames: int = 2,
        burst_face_cooldown_seconds: float = 0.45,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.burst_face_confirm_frames = max(2, min(6, int(burst_face_confirm_frames)))
        self.burst_face_cooldown_seconds = max(
            0.20,
            min(2.0, float(burst_face_cooldown_seconds)),
        )
        self._burst_face_target_id: int | None = None
        self._burst_face_direction = "-"
        self._burst_face_hits = 0
        self._burst_face_last_sent_at = -1e9
        self._burst_face_sent_signature: tuple[int | None, str] | None = None

    def reset(self) -> None:
        super().reset()
        self._reset_burst_face_evidence(clear_sent=True)
        self._burst_face_last_sent_at = -1e9

    def _reset_burst_face_evidence(self, *, clear_sent: bool = False) -> None:
        self._burst_face_target_id = None
        self._burst_face_direction = "-"
        self._burst_face_hits = 0
        if clear_sent:
            self._burst_face_sent_signature = None

    @staticmethod
    def _has_current_visual_authority(decision) -> bool:
        reason = str(getattr(decision, "reason", "")).casefold()
        return any(
            marker in reason
            for marker in (
                "mode=visible",
                "mode=occluded",
                "mode=contact_rebind",
            )
        )

    def plan(
        self,
        decision,
        *,
        now: float,
        movement_allowed: bool = True,
        block_reason: str = "",
    ):
        now = float(now)
        command = super().plan(
            decision,
            now=now,
            movement_allowed=movement_allowed,
            block_reason=block_reason,
        )

        # A normal frame ends the current burst episode. A future burst may authorize one fresh
        # correction again because knockback/particles may have physically changed facing.
        if movement_allowed:
            self._reset_burst_face_evidence(clear_sent=True)
            return command

        # Never weaken hard holds. Map-save resync must release every key; H settle must not add a
        # direction between face -> H -> settle sequencing.
        if command.safety_state in {"MAP_SAVE_RESYNC", "H_SETTLE_HOLD"}:
            self._reset_burst_face_evidence(clear_sent=True)
            return command
        if command.safety_state != "MOTION_BURST_HOLD":
            self._reset_burst_face_evidence(clear_sent=True)
            return command

        face_direction = self._direction_from_navigation(
            str(getattr(decision, "navigation", "")),
            "FACE",
        )
        distance = getattr(decision, "grid_distance", None)
        eligible = (
            str(getattr(decision, "mode", "")).upper() == "MELEE"
            and distance is not None
            and int(distance) <= 1
            and face_direction in _DIRECTION_KEYS
            and self._has_current_visual_authority(decision)
        )
        if not eligible:
            self._reset_burst_face_evidence(clear_sent=False)
            return command

        target_id = getattr(decision, "target_id", None)
        same_candidate = (
            target_id == self._burst_face_target_id
            and face_direction == self._burst_face_direction
        )
        if same_candidate:
            self._burst_face_hits += 1
        else:
            self._burst_face_target_id = target_id
            self._burst_face_direction = str(face_direction)
            self._burst_face_hits = 1

        signature = (target_id, str(face_direction))
        if self._burst_face_hits < self.burst_face_confirm_frames:
            return command
        if signature == self._burst_face_sent_signature:
            return command
        if now - self._burst_face_last_sent_at < self.burst_face_cooldown_seconds:
            return command

        self._burst_face_last_sent_at = now
        self._burst_face_sent_signature = signature
        self._last_face = str(face_direction)
        self._last_face_pulse = now
        self._force_face_confirmation = False

        return replace(
            command,
            face_pulse=_DIRECTION_KEYS[str(face_direction)],
            move_pulse=None,
            h_fire=False,
            h_shadow_ready=False,
            safety_state="BURST_FACE_CORRECT",
            reason=(
                f"visual adjacent target changed/confirmed facing during burst; "
                f"target={target_id} face={str(face_direction).lower()} / "
                f"corrigir orientacao visual no corpo-a-corpo durante particulas"
            ),
        )


# v0.3i remains the engine. v0.3j replaces only the recovery implementation with the narrow
# self-occlusion escape and the live planner with the particle-safe facing exception.
live_v03.PostCombatRecoveryEngine = SelfOcclusionFastChakraRecoveryEngine
live_v03.LiveCombatControlPlanner = BurstSafeMeleeFacingPlanner


def main() -> int:
    print("Kage Pilot v0.3j ROUND: BURST-SAFE FACING + TRAINER SELF-OCCLUSION ESCAPE")
    print("POST: recent adjacent trainer visual hidden -> one perpendicular pulse -> revalidate")
    print("V remains visual-only; memory never authorizes meditation / V exige visao atual")
    print("MOTION BURST: movement/H stay blocked; one confirmed adjacent visual face pulse allowed")
    print("MAP SAVE and H SETTLE remain absolute holds / bloqueios absolutos preservados")
    return round_v03i.main()


if __name__ == "__main__":
    raise SystemExit(main())
