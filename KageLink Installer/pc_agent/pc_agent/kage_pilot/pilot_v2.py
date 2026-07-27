from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .learning_v2 import CombatPrediction, IDLE_LABEL, TemporalCombatModel
from .pilot import Controller


@dataclass(frozen=True, slots=True)
class CombatStep:
    prediction: CombatPrediction
    applied_keys: tuple[str, ...]
    skill_fired: tuple[str, ...]


class TemporalCombatPilot:
    """Kage Pilot v0.2 runtime.

    R (or other configured base keys) remains held as the combat state.
    Navigation is predicted independently from skills. Skills are edge-like
    actions protected by both a cooldown and an idle rearm gate: after a jutsu
    fires, the skill policy must return to idle before the same jutsu can fire
    again. This prevents a classifier that gets stuck on H from spamming it.
    """

    def __init__(
        self,
        model: TemporalCombatModel,
        frame_source: Any,
        controller: Controller,
        *,
        nav_confidence: float = 0.0,
        skill_confidence: float = 0.02,
        decision_hz: float = 10.0,
        skill_cooldown_seconds: float = 1.2,
        startup_delay_seconds: float = 3.0,
        debug: bool = False,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    ) -> None:
        self.model = model
        self.frame_source = frame_source
        self.controller = controller
        self.nav_confidence = max(0.0, min(1.0, float(nav_confidence)))
        self.skill_confidence = max(0.0, min(1.0, float(skill_confidence)))
        self.decision_hz = max(1.0, min(30.0, float(decision_hz)))
        self.skill_cooldown_seconds = max(0.0, float(skill_cooldown_seconds))
        self.startup_delay_seconds = max(0.0, float(startup_delay_seconds))
        self.debug = bool(debug)
        self.sleep_fn = sleep_fn
        self.monotonic_fn = monotonic_fn
        self._previous_jpeg: bytes | None = None
        self._last_skill_fire: dict[str, float] = {}
        self._skill_rearmed = True
        self._last_debug_signature: tuple | None = None

    def reset(self) -> None:
        self._previous_jpeg = None
        self._last_skill_fire.clear()
        self._skill_rearmed = True
        self._last_debug_signature = None

    def _skill_allowed(self, label: str, now: float) -> bool:
        if label == IDLE_LABEL or not self._skill_rearmed:
            return False
        last = self._last_skill_fire.get(label)
        return last is None or now - last >= self.skill_cooldown_seconds

    def step(self) -> CombatStep:
        frame = self.frame_source.capture()
        current_jpeg = bytes(frame.jpeg)
        previous_jpeg = self._previous_jpeg or current_jpeg
        prediction = self.model.predict(previous_jpeg, current_jpeg)

        navigation = (
            prediction.navigation.keys
            if prediction.navigation.confidence >= self.nav_confidence
            else ()
        )

        now = self.monotonic_fn()
        skill_fired: tuple[str, ...] = ()

        if prediction.skill.label == IDLE_LABEL:
            self._skill_rearmed = True
        elif (
            prediction.skill.confidence >= self.skill_confidence
            and self._skill_allowed(prediction.skill.label, now)
        ):
            skill_fired = prediction.skill.keys
            if skill_fired:
                self._last_skill_fire[prediction.skill.label] = now
                self._skill_rearmed = False

        keys = tuple(sorted(set(self.model.base_keys).union(navigation).union(skill_fired)))
        self.controller.apply_keys(keys)
        self._previous_jpeg = current_jpeg

        if self.debug:
            signature = (
                prediction.navigation.label,
                round(prediction.navigation.confidence, 3),
                prediction.skill.label,
                round(prediction.skill.confidence, 3),
                keys,
                skill_fired,
                self._skill_rearmed,
            )
            if signature != self._last_debug_signature:
                print(
                    "V0.2 "
                    f"nav={prediction.navigation.label}:{prediction.navigation.confidence:.3f} "
                    f"skill={prediction.skill.label}:{prediction.skill.confidence:.3f} "
                    f"fire={'+'.join(skill_fired) or '-'} "
                    f"armed={'yes' if self._skill_rearmed else 'no'} "
                    f"keys={'+'.join(keys) or '-'}"
                )
                self._last_debug_signature = signature

        return CombatStep(prediction=prediction, applied_keys=keys, skill_fired=skill_fired)

    def run(self, *, seconds: float | None = None) -> int:
        self.reset()
        if self.startup_delay_seconds > 0:
            remaining = int(round(self.startup_delay_seconds))
            if remaining > 0:
                print(f"Kage Pilot v0.2 inicia em / starts in {remaining}s")
            self.sleep_fn(self.startup_delay_seconds)

        self.controller.activate()
        started = self.monotonic_fn()
        steps = 0
        try:
            while seconds is None or self.monotonic_fn() - started < float(seconds):
                self.step()
                steps += 1
                self.sleep_fn(1.0 / self.decision_hz)
        finally:
            self.controller.release_all()
        return steps
