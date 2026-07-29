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
    # held_keys deliberately contains only persistent/base keys (normally R). Directional
    # movement and H are emitted as short pulses and must be explicitly released by the
    # runtime after every pulse.
    held_keys: tuple[str, ...]
    face_pulse: str | None
    h_shadow_ready: bool
    reason: str
    move_pulse: str | None = None
    h_fire: bool = False
    safety_state: str = "OK"


@dataclass(frozen=True, slots=True)
class MotionBurstState:
    blocked: bool
    reason: str
    active_cells: int
    entities: int
    baseline_active_cells: float
    baseline_entities: float


class MotionBurstGuard:
    """Detect sudden scene-wide motion such as impact wind/particle bursts.

    Strong Shinobi Story attacks may emit many short-lived moving particles at once. They
    can look like multiple approaching entities for a few frames. This guard does not try
    to classify the effect visually; it notices the sudden *population spike* relative to
    the recent scene baseline and temporarily removes movement/skill authority while R stays on.
    """

    def __init__(
        self,
        *,
        hold_seconds: float = 0.75,
        active_multiplier: float = 2.8,
        entity_multiplier: float = 2.8,
        min_active_cells: int = 18,
        min_entities: int = 20,
        baseline_alpha: float = 0.08,
    ) -> None:
        self.hold_seconds = max(0.25, min(2.0, float(hold_seconds)))
        self.active_multiplier = max(1.5, min(8.0, float(active_multiplier)))
        self.entity_multiplier = max(1.5, min(8.0, float(entity_multiplier)))
        self.min_active_cells = max(4, int(min_active_cells))
        self.min_entities = max(4, int(min_entities))
        self.baseline_alpha = max(0.01, min(0.5, float(baseline_alpha)))
        self._baseline_active: float | None = None
        self._baseline_entities: float | None = None
        self._hold_until = -1e9

    def reset(self) -> None:
        self._baseline_active = None
        self._baseline_entities = None
        self._hold_until = -1e9

    def update(self, *, active_cells: int, entities: int, now: float) -> MotionBurstState:
        active = max(0, int(active_cells))
        entity_count = max(0, int(entities))
        now = float(now)

        if self._baseline_active is None:
            self._baseline_active = float(max(1, active))
        if self._baseline_entities is None:
            self._baseline_entities = float(max(1, entity_count))

        active_threshold = max(
            float(self.min_active_cells),
            float(self._baseline_active) * self.active_multiplier,
        )
        entity_threshold = max(
            float(self.min_entities),
            float(self._baseline_entities) * self.entity_multiplier,
        )

        active_spike = active >= active_threshold
        entity_spike = entity_count >= entity_threshold
        burst = active_spike or entity_spike
        if burst:
            self._hold_until = max(self._hold_until, now + self.hold_seconds)

        blocked = now < self._hold_until

        # Do not teach the baseline from a detected burst. Otherwise one giant impact
        # instantly becomes the new definition of normal motion.
        if not burst and not blocked:
            alpha = self.baseline_alpha
            self._baseline_active = (1.0 - alpha) * self._baseline_active + alpha * float(active)
            self._baseline_entities = (1.0 - alpha) * self._baseline_entities + alpha * float(entity_count)

        reasons: list[str] = []
        if active_spike:
            reasons.append(f"active_cells_spike={active}")
        if entity_spike:
            reasons.append(f"entities_spike={entity_count}")
        if blocked and not reasons:
            reasons.append("burst_settle")

        return MotionBurstState(
            blocked=blocked,
            reason="+".join(reasons) if reasons else "normal",
            active_cells=active,
            entities=entity_count,
            baseline_active_cells=float(self._baseline_active),
            baseline_entities=float(self._baseline_entities),
        )


class LiveCombatControlPlanner:
    """Translate v0.3 Shadow decisions into conservative real input.

    Safety policy:
    - R is the only continuously held combat key;
    - movement arrows are dead-man pulses, never continuous held state;
    - a distant target/direction must remain stable for several consecutive decisions
      before the first movement pulse;
    - movement is stopped if grid distance fails to improve for too long;
    - any motion burst or recovery movement arms a mandatory one-shot facing correction
      when melee resumes, covering knockback that physically turns the character;
    - real H is only fired in a validated melee skill window and always requests a fresh
      facing pulse immediately before the H pulse;
    - a motion-burst/skill-settle guard may veto movement, facing and H while R stays on.
    """

    def __init__(
        self,
        *,
        face_refresh_seconds: float = 0.45,
        move_confirm_frames: int = 2,
        max_no_progress_seconds: float = 1.15,
        no_progress_cooldown_seconds: float = 0.55,
        h_enabled: bool = False,
    ) -> None:
        self.face_refresh_seconds = max(0.15, min(2.0, float(face_refresh_seconds)))
        self.move_confirm_frames = max(2, min(6, int(move_confirm_frames)))
        self.max_no_progress_seconds = max(0.4, min(3.0, float(max_no_progress_seconds)))
        self.no_progress_cooldown_seconds = max(0.2, min(2.0, float(no_progress_cooldown_seconds)))
        self.h_enabled = bool(h_enabled)

        self._last_face = "-"
        self._last_face_pulse = -1e9
        self._move_target_id: int | None = None
        self._move_direction = "-"
        self._move_confirm_hits = 0
        self._move_best_distance: int | None = None
        self._move_last_progress_at = -1e9
        self._move_cooldown_until = -1e9
        self._force_face_confirmation = False

    def reset(self) -> None:
        self._last_face = "-"
        self._last_face_pulse = -1e9
        self._reset_move_evidence()
        self._move_cooldown_until = -1e9
        self._force_face_confirmation = False

    def _reset_move_evidence(self) -> None:
        self._move_target_id = None
        self._move_direction = "-"
        self._move_confirm_hits = 0
        self._move_best_distance = None
        self._move_last_progress_at = -1e9

    @staticmethod
    def _direction_from_navigation(navigation: str, prefix: str) -> str | None:
        value = str(navigation or "").upper()
        marker = prefix + "_"
        if not value.startswith(marker):
            return None
        direction = value[len(marker):]
        return direction if direction in _DIRECTION_KEYS else None

    def plan(
        self,
        decision,
        *,
        now: float,
        movement_allowed: bool = True,
        block_reason: str = "",
    ) -> LiveControlCommand:
        now = float(now)
        held: set[str] = set()
        if bool(decision.base_r):
            held.add("r")

        move_direction = self._direction_from_navigation(decision.navigation, "MOVE")
        face_direction = self._direction_from_navigation(decision.navigation, "FACE")
        face_pulse: str | None = None
        move_pulse: str | None = None
        h_fire = False
        safety_state = "OK"

        if not movement_allowed:
            self._reset_move_evidence()
            # A strong impact can physically turn the BYOND character. Once the scene
            # stabilizes, force one fresh facing pulse before trusting melee again.
            self._force_face_confirmation = True
            hold_state = "H_SETTLE_HOLD" if str(block_reason).startswith("h_settle") else "MOTION_BURST_HOLD"
            return LiveControlCommand(
                held_keys=tuple(sorted(held)),
                face_pulse=None,
                h_shadow_ready=False,
                reason=f"safety hold: {block_reason or 'blocked'}",
                move_pulse=None,
                h_fire=False,
                safety_state=hold_state,
            )

        if move_direction is not None:
            # Any recovery/approach means the next melee frame must explicitly re-face the
            # enemy once, even if the requested direction happens to equal the cached face.
            self._force_face_confirmation = True
            target_id = getattr(decision, "target_id", None)
            distance = getattr(decision, "grid_distance", None)
            distance_value = int(distance) if distance is not None else None

            same_candidate = (
                target_id == self._move_target_id
                and move_direction == self._move_direction
            )
            if not same_candidate:
                self._move_target_id = target_id
                self._move_direction = move_direction
                self._move_confirm_hits = 1
                self._move_best_distance = distance_value
                self._move_last_progress_at = now
                safety_state = "MOVE_CONFIRM"
            else:
                self._move_confirm_hits += 1

                if distance_value is not None:
                    if self._move_best_distance is None or distance_value < self._move_best_distance:
                        self._move_best_distance = distance_value
                        self._move_last_progress_at = now

                if now < self._move_cooldown_until:
                    safety_state = "MOVE_COOLDOWN"
                elif now - self._move_last_progress_at > self.max_no_progress_seconds:
                    self._move_cooldown_until = now + self.no_progress_cooldown_seconds
                    self._move_confirm_hits = 0
                    self._move_last_progress_at = now
                    safety_state = "NO_PROGRESS_HOLD"
                elif self._move_confirm_hits < self.move_confirm_frames:
                    safety_state = "MOVE_CONFIRM"
                else:
                    move_pulse = _DIRECTION_KEYS[move_direction]
                    safety_state = "MOVE_PULSE"
                    self._last_face = move_direction

        else:
            self._reset_move_evidence()
            if face_direction is not None:
                skill_requested = bool(self.h_enabled and decision.h_opportunity)
                force_face = self._force_face_confirmation or skill_requested
                should_refresh = (
                    force_face
                    or face_direction != self._last_face
                    or now - self._last_face_pulse >= self.face_refresh_seconds
                )
                if should_refresh:
                    face_pulse = _DIRECTION_KEYS[face_direction]
                    self._last_face_pulse = now
                    if self._force_face_confirmation and not skill_requested:
                        safety_state = "FACE_RECOVER"
                self._last_face = face_direction
                self._force_face_confirmation = False

                # H only fires if we can explicitly face a cardinal direction first. The
                # runtime executes face_pulse -> release -> H pulse -> release.
                if skill_requested and face_direction in _DIRECTION_KEYS:
                    h_fire = True
                    if face_pulse is None:
                        # Defensive invariant: every real H must be preceded by a fresh
                        # direction pulse, never only by cached facing state.
                        face_pulse = _DIRECTION_KEYS[face_direction]
                        self._last_face_pulse = now
                    safety_state = "H_FIRE"

        return LiveControlCommand(
            held_keys=tuple(sorted(held)),
            face_pulse=face_pulse,
            h_shadow_ready=bool(decision.h_opportunity),
            reason=str(decision.reason),
            move_pulse=move_pulse,
            h_fire=h_fire,
            safety_state=safety_state,
        )
