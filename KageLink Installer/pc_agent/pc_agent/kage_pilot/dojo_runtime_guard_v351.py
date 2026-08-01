from __future__ import annotations

import atexit
from typing import Any

from pc_agent.kage_pilot.dojo_debug_v351 import (
    DojoDebugOverlay,
    DojoDebugSnapshot,
    read_debug_settings,
)
from pc_agent.kage_pilot.meditation_guard_v351 import (
    ENTERING_MEDITATION,
    EXITING_MEDITATION,
    IDLE,
    MEDITATING,
    MeditationTransitionGuard,
    PROTECTED_MEDITATION_STATES,
)
from pc_agent.kage_pilot.post_combat_v03 import PostCombatDecision


def install_runtime_guard(runtime: Any):
    """Install meditation safety and debug over the current PR23 runtime class."""

    base_class = runtime.ClosedLoopVisualRecoveryEngine
    if bool(getattr(base_class, "_kagelink_v351_meditation_guard", False)):
        return base_class

    telemetry = runtime._telemetry

    class GuardedDojoRecoveryEngine(base_class):
        _kagelink_v351_meditation_guard = True

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            settings = read_debug_settings()
            self.meditation_guard = MeditationTransitionGuard(
                enter_delay_seconds=settings.meditation_enter_delay_seconds,
                exit_delay_seconds=settings.meditation_exit_delay_seconds,
                minimum_duration_seconds=settings.meditation_enter_delay_seconds,
                timeout_seconds=settings.meditation_timeout_seconds,
            )
            self._v351_recovery_hits = 0
            self._v351_last_health: float | None = None
            self._v351_last_chakra: float | None = None
            self._v351_last_leader_score: float | None = None
            self._v351_last_leader_distance: int | None = None
            self._v351_last_debug_state = ""
            self._v351_overlay = DojoDebugOverlay.from_environment()
            overlay_started = self._v351_overlay.start()
            atexit.register(self._v351_overlay.close)
            telemetry(
                "DOJO_DEBUG_OVERLAY_READY",
                {
                    "started": str(bool(overlay_started)).lower(),
                    "control": str(self._v351_overlay.control_path),
                },
            )

        def _refresh_meditation_settings(self) -> None:
            settings = read_debug_settings(self._v351_overlay.control_path)
            guard = self.meditation_guard
            if guard.phase != IDLE:
                return
            guard.enter_delay_seconds = settings.meditation_enter_delay_seconds
            guard.exit_delay_seconds = settings.meditation_exit_delay_seconds
            guard.minimum_duration_seconds = settings.meditation_enter_delay_seconds
            guard.timeout_seconds = settings.meditation_timeout_seconds

        def begin_post_combat(self) -> None:
            self.meditation_guard.reset()
            self._refresh_meditation_settings()
            self._v351_recovery_hits = 0
            self._v351_last_health = None
            self._v351_last_chakra = None
            self._v351_last_leader_score = None
            self._v351_last_leader_distance = None
            super().begin_post_combat()

        def can_start_next_combat(self) -> tuple[bool, str]:
            guard = self.meditation_guard
            if guard.phase in PROTECTED_MEDITATION_STATES:
                return False, "meditation_transition_active"
            if guard.abort_after_exit:
                return False, "meditation_recovery_aborted"
            if str(getattr(self, "state", "")) != "READY":
                return False, "post_combat_not_ready"
            return True, "ready"

        def _read_levels(self, frame_bgr):
            levels = self.resource_reader.read(frame_bgr)
            self._v351_last_health = levels.health
            self._v351_last_chakra = levels.chakra
            return levels

        def _levels_ready(self, levels) -> bool:
            return bool(
                levels.valid
                and float(levels.health or 0.0) >= float(self.health_target)
                and float(levels.chakra or 0.0) >= float(self.chakra_target)
            )

        def _meditation_decision(
            self,
            *,
            state: str,
            reason: str,
            tap_v: bool = False,
        ) -> PostCombatDecision:
            return PostCombatDecision(
                state=state,
                tap_v=tap_v,
                leader_score=self._v351_last_leader_score,
                leader_distance=self._v351_last_leader_distance,
                health=self._v351_last_health,
                chakra=self._v351_last_chakra,
                reason=reason,
            )

        @staticmethod
        def _arena_rect(observer_state) -> tuple[int, int, int, int] | None:
            value = getattr(observer_state, "arena_rect", None)
            if value is None or len(value) != 4:
                return None
            x0, y0, x1, y1 = (int(item) for item in value)
            return x0, y0, max(0, x1 - x0), max(0, y1 - y0)

        @staticmethod
        def _player_point(observer_state) -> tuple[float, float] | None:
            arena = getattr(observer_state, "arena_rect", None)
            center = getattr(observer_state, "player_center", None)
            if arena is None or center is None:
                return None
            return float(arena[0]) + float(center[0]), float(arena[1]) + float(center[1])

        def _publish_debug(self, frame_bgr, observer_state, decision, *, now: float, match=None) -> None:
            try:
                position = self.position.snapshot()
            except Exception:
                position = None
            guard = self.meditation_guard.snapshot(now)
            trainer_box = getattr(match, "bbox", None) if match is not None else None
            if trainer_box is None:
                current = getattr(self.leader_detector, "_last_visual", None)
                trainer_box = getattr(current, "bbox", None) if current is not None else None
            frame_height, frame_width = frame_bgr.shape[:2]
            allowed, blocked_reason = self.can_start_next_combat()
            if decision.state in PROTECTED_MEDITATION_STATES:
                blocked_reason = decision.reason or "meditation_transition_active"
            next_action = (
                "V"
                if decision.tap_v
                else str(decision.move_pulse or ("start next combat" if allowed else "hold"))
            )
            snapshot = DojoDebugSnapshot(
                timestamp=float(now),
                trainer_state=str(decision.state),
                hp=decision.health if decision.health is not None else self._v351_last_health,
                chakra=(
                    decision.chakra
                    if decision.chakra is not None
                    else self._v351_last_chakra
                ),
                meditation_state=guard.phase,
                meditation_elapsed=guard.elapsed,
                v_cooldown_remaining=guard.cooldown_remaining,
                position_state=(position.state.value if position is not None else "LOST"),
                position_x=(float(position.x) if position is not None else 0.0),
                position_y=(float(position.y) if position is not None else 0.0),
                position_confidence=(
                    float(position.confidence) if position is not None else 0.0
                ),
                trainer_box=trainer_box,
                arena_rect=self._arena_rect(observer_state),
                player_point=self._player_point(observer_state),
                frame_size=(int(frame_width), int(frame_height)),
                last_action="V" if decision.tap_v else str(decision.move_pulse or "hold"),
                next_action=next_action,
                blocked_reason="" if allowed else blocked_reason,
                combat_start_allowed=allowed,
            )
            self._v351_overlay.publish(snapshot)

        def _emit_guard_state(self, decision: PostCombatDecision, *, now: float) -> None:
            guard = self.meditation_guard.snapshot(now)
            marker = (
                f"{decision.state}:{guard.phase}:{guard.cooldown_remaining:.2f}:"
                f"{self._v351_recovery_hits}"
            )
            if marker == self._v351_last_debug_state:
                return
            self._v351_last_debug_state = marker
            telemetry(
                "DOJO_MEDITATION_STATE",
                {
                    "state": guard.phase,
                    "decision": decision.state,
                    "elapsed": f"{guard.elapsed:.2f}",
                    "cooldown": f"{guard.cooldown_remaining:.2f}",
                    "hp": "-" if self._v351_last_health is None else f"{self._v351_last_health:.3f}",
                    "chakra": "-" if self._v351_last_chakra is None else f"{self._v351_last_chakra:.3f}",
                },
            )
            allowed, reason = self.can_start_next_combat()
            if not allowed:
                telemetry("DOJO_COMBAT_START_BLOCKED", {"reason": reason, "state": guard.phase})

        def observe_world(self, frame_bgr, observer_state, observer, *, now: float):
            match = super().observe_world(frame_bgr, observer_state, observer, now=now)
            decision = PostCombatDecision(
                state="IN_COMBAT",
                leader_score=getattr(match, "score", None),
                reason="combat observation / observacao de combate",
            )
            self._publish_debug(frame_bgr, observer_state, decision, now=float(now), match=match)
            return match

        def step(self, frame_bgr, observer_state, observer, *, now: float):
            now = float(now)
            transition = self.meditation_guard.advance(now)
            if transition == "entered":
                self.state = "MEDITATING"
                telemetry(
                    "DOJO_MEDITATION_ENTER_CONFIRMED",
                    {"elapsed": f"{self.meditation_guard.elapsed(now):.2f}"},
                )
            elif transition == "exited":
                if self.meditation_guard.abort_after_exit:
                    telemetry("DOJO_RECOVERY_ABORTED", {"reason": "meditation_timeout"})
                    raise RuntimeError("MEDITATION_RECOVERY_TIMEOUT")
                self.state = "READY"
                decision = self._meditation_decision(
                    state="READY",
                    reason="meditation exit delay completed / saida da meditacao concluida",
                )
                telemetry("DOJO_MEDITATION_EXIT_CONFIRMED", {"state": "READY"})
                self._emit_guard_state(decision, now=now)
                self._publish_debug(frame_bgr, observer_state, decision, now=now)
                return decision

            guard_phase = self.meditation_guard.phase
            if guard_phase == ENTERING_MEDITATION:
                self._read_levels(frame_bgr)
                decision = self._meditation_decision(
                    state=ENTERING_MEDITATION,
                    reason=(
                        "waiting protected V enter delay / "
                        "aguardando delay protegido para entrar em meditacao"
                    ),
                )
                self._emit_guard_state(decision, now=now)
                self._publish_debug(frame_bgr, observer_state, decision, now=now)
                return decision

            if guard_phase == EXITING_MEDITATION:
                self._read_levels(frame_bgr)
                decision = self._meditation_decision(
                    state=EXITING_MEDITATION,
                    reason=(
                        "waiting protected V exit delay / "
                        "aguardando delay protegido para sair da meditacao"
                    ),
                )
                self._emit_guard_state(decision, now=now)
                self._publish_debug(frame_bgr, observer_state, decision, now=now)
                return decision

            if guard_phase == MEDITATING:
                self.state = "MEDITATING"
                levels = self._read_levels(frame_bgr)
                if self.meditation_guard.timed_out(now):
                    if self.meditation_guard.request_exit(now, abort_after_exit=True):
                        decision = self._meditation_decision(
                            state=EXITING_MEDITATION,
                            tap_v=True,
                            reason="meditation timeout; safe V exit requested / timeout; saida segura",
                        )
                        telemetry(
                            "DOJO_MEDITATION_TIMEOUT",
                            {"action": "safe_exit", "elapsed": f"{self.meditation_guard.elapsed(now):.2f}"},
                        )
                        self._emit_guard_state(decision, now=now)
                        self._publish_debug(frame_bgr, observer_state, decision, now=now)
                        return decision
                    decision = self._meditation_decision(
                        state="MEDITATION_TIMEOUT",
                        reason="meditation timeout; V cooldown active / timeout; cooldown de V ativo",
                    )
                    self._emit_guard_state(decision, now=now)
                    self._publish_debug(frame_bgr, observer_state, decision, now=now)
                    return decision

                if self._levels_ready(levels):
                    self._v351_recovery_hits += 1
                else:
                    self._v351_recovery_hits = 0

                if self._v351_recovery_hits >= int(self.recovery_confirm_frames):
                    if self.meditation_guard.request_exit(now):
                        decision = self._meditation_decision(
                            state=EXITING_MEDITATION,
                            tap_v=True,
                            reason=(
                                "recovery confirmed; protected V exit requested / "
                                "recuperacao confirmada; saida protegida solicitada"
                            ),
                        )
                        telemetry(
                            "DOJO_MEDITATION_EXIT_REQUESTED",
                            {
                                "hp": f"{float(levels.health or 0.0):.3f}",
                                "chakra": f"{float(levels.chakra or 0.0):.3f}",
                                "delay": f"{self.meditation_guard.exit_delay_seconds:.2f}",
                            },
                        )
                        self._emit_guard_state(decision, now=now)
                        self._publish_debug(frame_bgr, observer_state, decision, now=now)
                        return decision
                    telemetry(
                        "DOJO_MEDITATION_V_BLOCKED",
                        {
                            "reason": "minimum_duration_or_cooldown",
                            "remaining": f"{self.meditation_guard.cooldown_remaining(now):.2f}",
                        },
                    )

                decision = self._meditation_decision(
                    state=MEDITATING,
                    reason=(
                        f"meditating HP={float(levels.health or 0.0)*100:.0f}% "
                        f"Chakra={float(levels.chakra or 0.0)*100:.0f}%"
                    ),
                )
                self._emit_guard_state(decision, now=now)
                self._publish_debug(frame_bgr, observer_state, decision, now=now)
                return decision

            self._refresh_meditation_settings()
            decision = super().step(frame_bgr, observer_state, observer, now=now)
            self._v351_last_leader_score = decision.leader_score
            self._v351_last_leader_distance = decision.leader_distance

            if decision.tap_v and decision.state == "START_MEDITATION":
                levels = self._read_levels(frame_bgr)
                if self._levels_ready(levels):
                    self.state = "READY"
                    decision = self._meditation_decision(
                        state="READY",
                        reason=(
                            "resources already satisfy recovery targets; meditation skipped / "
                            "recursos ja atendem as metas; meditacao ignorada"
                        ),
                    )
                    telemetry(
                        "DOJO_MEDITATION_SKIPPED",
                        {
                            "hp": f"{float(levels.health or 0.0):.3f}",
                            "chakra": f"{float(levels.chakra or 0.0):.3f}",
                        },
                    )
                    self._publish_debug(frame_bgr, observer_state, decision, now=now)
                    return decision

                if not self.meditation_guard.request_enter(now):
                    self.state = "MEDITATING"
                    decision = self._meditation_decision(
                        state=MEDITATING,
                        reason="V enter request blocked by cooldown / entrada V bloqueada por cooldown",
                    )
                    telemetry(
                        "DOJO_MEDITATION_V_BLOCKED",
                        {
                            "reason": "enter_cooldown",
                            "remaining": f"{self.meditation_guard.cooldown_remaining(now):.2f}",
                        },
                    )
                    self._emit_guard_state(decision, now=now)
                    self._publish_debug(frame_bgr, observer_state, decision, now=now)
                    return decision

                decision = self._meditation_decision(
                    state=ENTERING_MEDITATION,
                    tap_v=True,
                    reason=(
                        "protected V enter requested / "
                        "entrada protegida em meditacao solicitada"
                    ),
                )
                telemetry(
                    "DOJO_MEDITATION_ENTER_REQUESTED",
                    {
                        "hp": "-" if levels.health is None else f"{levels.health:.3f}",
                        "chakra": "-" if levels.chakra is None else f"{levels.chakra:.3f}",
                        "delay": f"{self.meditation_guard.enter_delay_seconds:.2f}",
                    },
                )
                self._emit_guard_state(decision, now=now)
                self._publish_debug(frame_bgr, observer_state, decision, now=now)
                return decision

            if decision.tap_v:
                telemetry(
                    "DOJO_MEDITATION_V_BLOCKED",
                    {"reason": "unowned_v_request", "state": decision.state},
                )
                decision = PostCombatDecision(
                    state=decision.state,
                    move_pulse=decision.move_pulse,
                    tap_v=False,
                    leader_score=decision.leader_score,
                    leader_distance=decision.leader_distance,
                    health=decision.health,
                    chakra=decision.chakra,
                    reason=decision.reason + " / V blocked by 3.5.1 guard",
                )

            self._publish_debug(frame_bgr, observer_state, decision, now=now)
            return decision

    GuardedDojoRecoveryEngine.__name__ = "GuardedDojoRecoveryEngine"
    GuardedDojoRecoveryEngine.__qualname__ = "GuardedDojoRecoveryEngine"
    runtime.ClosedLoopVisualRecoveryEngine = GuardedDojoRecoveryEngine
    runtime.live_runtime.PostCombatRecoveryEngine = GuardedDojoRecoveryEngine
    telemetry(
        "DOJO_MEDITATION_GUARD_INSTALLED",
        {"base": base_class.__name__, "enter_delay_min": "5.0"},
    )
    return GuardedDojoRecoveryEngine


__all__ = ["install_runtime_guard"]
