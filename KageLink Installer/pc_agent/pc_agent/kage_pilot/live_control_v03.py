from __future__ import annotations

from dataclasses import dataclass


_DIRECTION_KEYS = {
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
}


@dataclass(frozen=True, slots=True)
class LiveControlCommand:
    held_keys: tuple[str, ...]
    face_pulse: str | None
    h_shadow_ready: bool
    reason: str


class LiveCombatControlPlanner:
    """Translate v0.3 Shadow decisions into conservative real input.

    Safety/validation policy for the first live-control gate:
    - R follows the logical combat session and uses the already validated BYOND repeat hold;
    - MOVE_* may hold one cardinal direction together with R;
    - FACE_* never holds movement continuously. It emits only a short pulse when facing
      changes (or after a modest refresh interval), reducing unwanted walking in melee;
    - H remains shadow-only in this stage and is never returned as a real key.
    """

    def __init__(self, *, face_refresh_seconds: float = 0.45) -> None:
        self.face_refresh_seconds = max(0.15, min(2.0, float(face_refresh_seconds)))
        self._last_face = "-"
        self._last_face_pulse = -1e9

    def reset(self) -> None:
        self._last_face = "-"
        self._last_face_pulse = -1e9

    @staticmethod
    def _direction_from_navigation(navigation: str, prefix: str) -> str | None:
        value = str(navigation or "").upper()
        marker = prefix + "_"
        if not value.startswith(marker):
            return None
        direction = value[len(marker):]
        return direction if direction in _DIRECTION_KEYS else None

    def plan(self, decision, *, now: float) -> LiveControlCommand:
        held: set[str] = set()
        if bool(decision.base_r):
            held.add("r")

        move_direction = self._direction_from_navigation(decision.navigation, "MOVE")
        face_direction = self._direction_from_navigation(decision.navigation, "FACE")
        face_pulse: str | None = None

        if move_direction is not None:
            held.add(_DIRECTION_KEYS[move_direction])
            self._last_face = move_direction
        elif face_direction is not None:
            should_refresh = (
                face_direction != self._last_face
                or float(now) - self._last_face_pulse >= self.face_refresh_seconds
            )
            if should_refresh:
                face_pulse = _DIRECTION_KEYS[face_direction]
                self._last_face_pulse = float(now)
            self._last_face = face_direction

        return LiveControlCommand(
            held_keys=tuple(sorted(held)),
            face_pulse=face_pulse,
            h_shadow_ready=bool(decision.h_opportunity),
            reason=str(decision.reason),
        )
