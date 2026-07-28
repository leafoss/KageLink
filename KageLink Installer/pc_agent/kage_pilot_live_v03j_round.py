from __future__ import annotations

from dataclasses import replace

import kage_pilot_live_v03 as live_v03
import kage_pilot_live_v03i_round as round_v03i  # applies validated v0.3i patches first


_DIRECTION_KEYS = {
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
}

_PREVIOUS_PLANNER = live_v03.LiveCombatControlPlanner


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


# v0.3i remains the engine. v0.3j replaces only the live-control planner with the narrow
# visual-melee facing exception above.
live_v03.LiveCombatControlPlanner = BurstSafeMeleeFacingPlanner


def main() -> int:
    print("Kage Pilot v0.3j ROUND: BURST-SAFE VISUAL MELEE FACING")
    print("MOTION BURST: movement/H stay blocked; one confirmed adjacent visual face pulse allowed")
    print("MAP SAVE and H SETTLE remain absolute holds / bloqueios absolutos preservados")
    return round_v03i.main()


if __name__ == "__main__":
    raise SystemExit(main())
