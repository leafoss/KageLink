from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .models import NavigationState


@dataclass(frozen=True, slots=True)
class StateTransition:
    previous: NavigationState
    current: NavigationState
    reason: str
    timestamp: str


class InvalidTransition(RuntimeError):
    pass


_ALLOWED: dict[NavigationState, set[NavigationState]] = {
    NavigationState.IDLE: {NavigationState.PLANNING, NavigationState.OBSERVING, NavigationState.TEACHING, NavigationState.ABORTED},
    NavigationState.PLANNING: {NavigationState.NAVIGATING, NavigationState.ARRIVED, NavigationState.ERROR, NavigationState.ABORTED},
    NavigationState.NAVIGATING: {NavigationState.VERIFYING_PROGRESS, NavigationState.STUCK, NavigationState.ARRIVED, NavigationState.PAUSED, NavigationState.ABORTED, NavigationState.ERROR},
    NavigationState.VERIFYING_PROGRESS: {NavigationState.NAVIGATING, NavigationState.STUCK, NavigationState.RELOCALIZING, NavigationState.ARRIVED, NavigationState.ERROR},
    NavigationState.STUCK: {NavigationState.RECOVERING, NavigationState.PAUSED, NavigationState.ABORTED},
    NavigationState.RECOVERING: {NavigationState.PLANNING, NavigationState.RELOCALIZING, NavigationState.PAUSED, NavigationState.ABORTED, NavigationState.ERROR},
    NavigationState.RELOCALIZING: {NavigationState.PLANNING, NavigationState.PAUSED, NavigationState.ABORTED, NavigationState.ERROR},
    NavigationState.PAUSED: {NavigationState.PLANNING, NavigationState.NAVIGATING, NavigationState.ABORTED},
    NavigationState.OBSERVING: {NavigationState.IDLE, NavigationState.PAUSED, NavigationState.ABORTED, NavigationState.ERROR},
    NavigationState.TEACHING: {NavigationState.IDLE, NavigationState.PAUSED, NavigationState.ABORTED, NavigationState.ERROR},
    NavigationState.ARRIVED: {NavigationState.IDLE},
    NavigationState.ABORTED: {NavigationState.IDLE},
    NavigationState.ERROR: {NavigationState.IDLE, NavigationState.ABORTED},
    NavigationState.WAITING_FOR_WINDOW: {NavigationState.OBSERVING, NavigationState.ERROR, NavigationState.ABORTED},
    NavigationState.LOCALIZING: {NavigationState.PLANNING, NavigationState.RELOCALIZING, NavigationState.ERROR, NavigationState.ABORTED},
    NavigationState.VERIFYING_TRANSITION: {NavigationState.LOCALIZING, NavigationState.NAVIGATING, NavigationState.ERROR, NavigationState.ABORTED},
}


class NavigationStateMachine:
    def __init__(self, listener: Callable[[StateTransition], None] | None = None) -> None:
        self.state = NavigationState.IDLE
        self.history: list[StateTransition] = []
        self._listener = listener

    def transition(self, new_state: NavigationState, reason: str) -> StateTransition:
        if new_state == self.state:
            event = StateTransition(self.state, new_state, reason, datetime.now(timezone.utc).isoformat())
            self.history.append(event)
            if self._listener:
                self._listener(event)
            return event
        if new_state not in _ALLOWED.get(self.state, set()):
            raise InvalidTransition(f"{self.state.value} -> {new_state.value} is not allowed")
        event = StateTransition(self.state, new_state, reason, datetime.now(timezone.utc).isoformat())
        self.state = new_state
        self.history.append(event)
        if self._listener:
            self._listener(event)
        return event
