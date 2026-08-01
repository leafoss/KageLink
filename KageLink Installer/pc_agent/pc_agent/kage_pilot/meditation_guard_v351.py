from __future__ import annotations

from dataclasses import dataclass


ENTERING_MEDITATION = "ENTERING_MEDITATION"
MEDITATING = "MEDITATING"
EXITING_MEDITATION = "EXITING_MEDITATION"
IDLE = "IDLE"
PROTECTED_MEDITATION_STATES = frozenset(
    {ENTERING_MEDITATION, MEDITATING, EXITING_MEDITATION}
)


@dataclass(frozen=True, slots=True)
class MeditationGuardSnapshot:
    phase: str
    elapsed: float
    cooldown_remaining: float
    transition_remaining: float
    timed_out: bool
    combat_allowed: bool


class MeditationTransitionGuard:
    """Non-blocking V transition authority for the Dojo meditation toggle.

    Sending V is an intention. A transition is complete only after its protected
    interval has elapsed. The caller remains responsible for observing resources.
    """

    def __init__(
        self,
        *,
        enter_delay_seconds: float = 5.5,
        exit_delay_seconds: float = 5.5,
        minimum_duration_seconds: float = 5.5,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.enter_delay_seconds = max(5.0, min(30.0, float(enter_delay_seconds)))
        self.exit_delay_seconds = max(5.0, min(30.0, float(exit_delay_seconds)))
        self.minimum_duration_seconds = max(
            self.enter_delay_seconds,
            min(60.0, float(minimum_duration_seconds)),
        )
        self.timeout_seconds = max(15.0, min(1800.0, float(timeout_seconds)))
        self.reset()

    def reset(self) -> None:
        self.phase = IDLE
        self.started_at: float | None = None
        self.last_v_at: float | None = None
        self.transition_until: float | None = None
        self.abort_after_exit = False

    @property
    def protected(self) -> bool:
        return self.phase in PROTECTED_MEDITATION_STATES

    @property
    def combat_allowed(self) -> bool:
        return not self.protected and not self.abort_after_exit

    def elapsed(self, now: float) -> float:
        if self.started_at is None:
            return 0.0
        return max(0.0, float(now) - self.started_at)

    def transition_remaining(self, now: float) -> float:
        if self.transition_until is None:
            return 0.0
        return max(0.0, self.transition_until - float(now))

    def cooldown_remaining(self, now: float) -> float:
        return self.transition_remaining(now)

    def request_enter(self, now: float) -> bool:
        now = float(now)
        if self.protected or self.cooldown_remaining(now) > 0.0:
            return False
        self.phase = ENTERING_MEDITATION
        self.started_at = now
        self.last_v_at = now
        self.transition_until = now + self.enter_delay_seconds
        self.abort_after_exit = False
        return True

    def request_exit(self, now: float, *, abort_after_exit: bool = False) -> bool:
        now = float(now)
        if self.phase != MEDITATING:
            return False
        if self.elapsed(now) < self.minimum_duration_seconds:
            return False
        if self.cooldown_remaining(now) > 0.0:
            return False
        self.phase = EXITING_MEDITATION
        self.last_v_at = now
        self.transition_until = now + self.exit_delay_seconds
        self.abort_after_exit = bool(abort_after_exit)
        return True

    def advance(self, now: float) -> str | None:
        now = float(now)
        if self.transition_remaining(now) > 0.0:
            return None
        if self.phase == ENTERING_MEDITATION:
            self.phase = MEDITATING
            self.transition_until = None
            return "entered"
        if self.phase == EXITING_MEDITATION:
            self.phase = IDLE
            self.transition_until = None
            return "exited"
        return None

    def timed_out(self, now: float) -> bool:
        return self.phase in {ENTERING_MEDITATION, MEDITATING} and self.elapsed(now) >= self.timeout_seconds

    def snapshot(self, now: float) -> MeditationGuardSnapshot:
        return MeditationGuardSnapshot(
            phase=self.phase,
            elapsed=self.elapsed(now),
            cooldown_remaining=self.cooldown_remaining(now),
            transition_remaining=self.transition_remaining(now),
            timed_out=self.timed_out(now),
            combat_allowed=self.combat_allowed,
        )
