from __future__ import annotations

import argparse
import json
import sys

import kage_pilot_live_v03 as live_v03
import kage_pilot_live_v03j_round as round_v03j  # installs validated v0.3j patches first

from pc_agent.kage_pilot.dojo_leader_v03l import install_clear_dojo_leader_detector
from pc_agent.kage_pilot.ko_identity_v03k import RoundKOIdentityGate


install_clear_dojo_leader_detector()

_BASE_WATCHER = live_v03.ChatVictoryWatcher
_BASE_OBSERVER = live_v03.ParticleSafeGridTargetObserver
_BASE_ENGINE = live_v03.ShadowCombatDecisionEngine
_BASE_PLANNER = live_v03.LiveCombatControlPlanner
_BASE_BURST_GUARD = live_v03.MotionBurstGuard
_BASE_CONTROLLER = live_v03.WindowsGameController

_GATE = RoundKOIdentityGate()
_REJECTION_GENERATION = 0
_ACTIVE_CONTROLLER = None


def _quoted(value: str | None) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _configure_round(previous_ko_name: str | None) -> None:
    global _GATE, _REJECTION_GENERATION, _ACTIVE_CONTROLLER
    _GATE = RoundKOIdentityGate(previous_ko_name, required_visual_hits=2)
    _REJECTION_GENERATION = 0
    _ACTIVE_CONTROLLER = None


def _reject_current_target() -> None:
    global _REJECTION_GENERATION
    controller = _ACTIVE_CONTROLLER
    if controller is not None:
        try:
            controller.release_all()
        except Exception:
            pass
    _GATE.reset_current_enemy_evidence()
    _REJECTION_GENERATION += 1


class OpponentAwareVictoryWatcher(_BASE_WATCHER):
    """Accept only a different opponent KO after current-round visual enemy evidence."""

    def poll(self):
        signal = super().poll()
        if signal is None:
            return None

        decision = _GATE.evaluate(signal.text)
        print(
            f"KO_CANDIDATE name={_quoted(decision.candidate_name)} "
            f"previous={_quoted(decision.previous_name)} "
            f"visual_hits={decision.visual_enemy_hits}"
        )

        if decision.accepted:
            print(
                f"KO_ACCEPTED reason={decision.reason} "
                f"previous={_quoted(decision.previous_name)} "
                f"current={_quoted(decision.candidate_name)}"
            )
            return signal

        _reject_current_target()
        print(
            f"KO_REJECTED reason={decision.reason} "
            f"previous={_quoted(decision.previous_name)} "
            f"current={_quoted(decision.candidate_name)}"
        )
        print("TARGET_INVALIDATED reason=KO_IDENTITY_REJECTED")
        print("COMBAT_CONTINUES / COMBATE_CONTINUA: reacquire another current visual target")
        return None


class OpponentAwareObserver(_BASE_OBSERVER):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ko_rejection_generation = _REJECTION_GENERATION

    def process(self, *args, **kwargs):
        if self._ko_rejection_generation != _REJECTION_GENERATION:
            self.reset()
            self._ko_rejection_generation = _REJECTION_GENERATION
        return super().process(*args, **kwargs)


class OpponentAwareCombatEngine(_BASE_ENGINE):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ko_rejection_generation = _REJECTION_GENERATION

    def decide(self, state, observer, tracker, *, now: float, skills_allowed: bool = True):
        if self._ko_rejection_generation != _REJECTION_GENERATION:
            self.reset()
            self._ko_rejection_generation = _REJECTION_GENERATION
        decision = super().decide(
            state,
            observer,
            tracker,
            now=now,
            skills_allowed=skills_allowed,
        )
        _GATE.observe_target(
            target_id=getattr(decision, "target_id", None),
            target_mode=getattr(observer, "target_mode", "NONE"),
        )
        return decision


class OpponentAwarePlanner(_BASE_PLANNER):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ko_rejection_generation = _REJECTION_GENERATION

    def plan(self, *args, **kwargs):
        if self._ko_rejection_generation != _REJECTION_GENERATION:
            self.reset()
            self._ko_rejection_generation = _REJECTION_GENERATION
        return super().plan(*args, **kwargs)


class OpponentAwareBurstGuard(_BASE_BURST_GUARD):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ko_rejection_generation = _REJECTION_GENERATION

    def update(self, *args, **kwargs):
        if self._ko_rejection_generation != _REJECTION_GENERATION:
            self.reset()
            self._ko_rejection_generation = _REJECTION_GENERATION
        return super().update(*args, **kwargs)


class OpponentAwareController(_BASE_CONTROLLER):
    def __init__(self, *args, **kwargs) -> None:
        global _ACTIVE_CONTROLLER
        super().__init__(*args, **kwargs)
        _ACTIVE_CONTROLLER = self

    def close(self) -> None:
        global _ACTIVE_CONTROLLER
        try:
            super().close()
        finally:
            if _ACTIVE_CONTROLLER is self:
                _ACTIVE_CONTROLLER = None


# Preserve the validated v0.3j runtime and replace only the cross-round KO authority boundary.
live_v03.ChatVictoryWatcher = OpponentAwareVictoryWatcher
live_v03.ParticleSafeGridTargetObserver = OpponentAwareObserver
live_v03.ShadowCombatDecisionEngine = OpponentAwareCombatEngine
live_v03.LiveCombatControlPlanner = OpponentAwarePlanner
live_v03.MotionBurstGuard = OpponentAwareBurstGuard
live_v03.WindowsGameController = OpponentAwareController


def _extract_internal_args(argv: list[str]) -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--previous-ko-name", default="")
    known, remaining = parser.parse_known_args(argv)
    return str(known.previous_ko_name or ""), list(remaining)


def main() -> int:
    previous_name, remaining = _extract_internal_args(sys.argv[1:])
    sys.argv = [sys.argv[0], *remaining]
    _configure_round(previous_name)

    print("Kage Pilot v0.3j HOTFIX: OPPONENT-AWARE KO IDENTITY BUFFER")
    print("TRAINER: local calibration + clearer bundled 32x45 template")
    print(
        f"KO BUFFER previous={_quoted(previous_name or None)}; "
        "same opponent KO is rejected and combat continues"
    )
    print("KO ACCEPT: different name + two current visual enemy observations")
    print("KO REJECT: release all -> invalidate target memory -> reacquire another enemy")
    return round_v03j.main()


if __name__ == "__main__":
    raise SystemExit(main())
