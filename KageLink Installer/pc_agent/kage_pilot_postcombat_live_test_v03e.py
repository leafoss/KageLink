from __future__ import annotations

import time

import kage_pilot_postcombat_live_test_v03c as harness

from pc_agent.kage_pilot.post_combat_v03e import ObstacleAwarePostCombatRecoveryEngine


_DIRECTIONS = {"up", "right", "down", "left"}
_OriginalObserver = harness.ParticleSafeGridTargetObserver
_OriginalController = harness.WindowsGameController
_ACTIVE_ENGINE: ObstacleAwarePostCombatRecoveryEngine | None = None


class ActiveEngine(ObstacleAwarePostCombatRecoveryEngine):
    def __init__(self, *args, **kwargs) -> None:
        global _ACTIVE_ENGINE
        super().__init__(*args, **kwargs)
        self.begin_post_combat()
        _ACTIVE_ENGINE = self


class MovementObserver(_OriginalObserver):
    def process(self, frame_bgr, *, timestamp=None):
        state = super().process(frame_bgr, timestamp=timestamp)
        engine = _ACTIVE_ENGINE
        if engine is not None:
            engine.observe_movement_frame(frame_bgr, state, now=state.timestamp)
        return state


class MovementController(_OriginalController):
    def apply_keys(self, keys: tuple[str, ...]) -> None:
        normalized = {str(key).strip().lower() for key in keys if str(key).strip()}
        engine = _ACTIVE_ENGINE
        if engine is not None and len(normalized) == 1 and normalized.issubset(_DIRECTIONS):
            engine.arm_movement_probe(next(iter(normalized)), now=time.monotonic())
        super().apply_keys(keys)


_OriginalLine = harness._line


def _line_with_motion(decision) -> str:
    text = _OriginalLine(decision)
    engine = _ACTIVE_ENGINE
    if engine is None or engine.last_movement_detected is None:
        return text + " motion=-"
    moved = "yes" if engine.last_movement_detected else "no"
    return (
        text
        + f" motion={moved}:{engine.last_movement_direction}"
        + f" flow={engine.last_flow_magnitude:.1f}"
        + f" diff={engine.last_frame_difference:.1f}"
    )


harness.PostCombatRecoveryEngineV3 = ActiveEngine
harness.ParticleSafeGridTargetObserver = MovementObserver
harness.WindowsGameController = MovementController
harness._line = _line_with_motion


def main() -> int:
    print("Kage Pilot v0.3e OBSTACLE-AWARE OFF-SCREEN SEARCH TEST")
    print("NO MOTION TWICE -> TEMPORARY BLOCK -> NEXT DIRECTION")
    return harness.main()


if __name__ == "__main__":
    raise SystemExit(main())
