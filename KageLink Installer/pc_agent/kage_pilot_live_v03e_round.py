from __future__ import annotations

import time

import kage_pilot_live_v03 as live_v03

from pc_agent.kage_pilot.post_combat_v03c import PersistentDojoLeaderDetector
from pc_agent.kage_pilot.post_combat_v03e import ObstacleAwarePostCombatRecoveryEngine


_DIRECTIONS = {"up", "right", "down", "left"}
_OriginalObserver = live_v03.ParticleSafeGridTargetObserver
_OriginalVictoryWatcher = live_v03.ChatVictoryWatcher
_OriginalController = live_v03.WindowsGameController
_ACTIVE_RECOVERY_ENGINE: ObstacleAwarePostCombatRecoveryEngine | None = None


class ActiveObstacleRecoveryEngine(ObstacleAwarePostCombatRecoveryEngine):
    def __init__(self, *args, **kwargs) -> None:
        global _ACTIVE_RECOVERY_ENGINE
        super().__init__(*args, **kwargs)
        _ACTIVE_RECOVERY_ENGINE = self


class MovementAndAnchorObserver(_OriginalObserver):
    """Track the trainer during combat and evaluate post-combat movement after each pulse."""

    def process(self, frame_bgr, *, timestamp=None):
        state = super().process(frame_bgr, timestamp=timestamp)
        engine = _ACTIVE_RECOVERY_ENGINE
        if engine is not None:
            if engine.post_started:
                engine.observe_movement_frame(frame_bgr, state, now=state.timestamp)
            else:
                engine.observe_world(frame_bgr, state, self, now=state.timestamp)
        return state


class MovementProbeController(_OriginalController):
    """Arm a no-motion probe only for post-combat dead-man arrow pulses."""

    def apply_keys(self, keys: tuple[str, ...]) -> None:
        normalized = {str(key).strip().lower() for key in keys if str(key).strip()}
        engine = _ACTIVE_RECOVERY_ENGINE
        if (
            engine is not None
            and engine.post_started
            and len(normalized) == 1
            and normalized.issubset(_DIRECTIONS)
        ):
            engine.arm_movement_probe(next(iter(normalized)), now=time.monotonic())
        super().apply_keys(keys)


class VictoryTransitionWatcher(_OriginalVictoryWatcher):
    def poll(self):
        signal = super().poll()
        if signal is not None and _ACTIVE_RECOVERY_ENGINE is not None:
            _ACTIVE_RECOVERY_ENGINE.begin_post_combat()
        return signal


# Combat inference/control is unchanged. Only read-only trainer anchoring, post-combat obstacle
# feedback and route choice are replaced.
live_v03.ParticleSafeGridTargetObserver = MovementAndAnchorObserver
live_v03.ChatVictoryWatcher = VictoryTransitionWatcher
live_v03.WindowsGameController = MovementProbeController
live_v03.DojoLeaderDetector = PersistentDojoLeaderDetector
live_v03.PostCombatRecoveryEngine = ActiveObstacleRecoveryEngine


def main() -> int:
    print("Kage Pilot v0.3e ROUND: OBSTACLE-AWARE RETURN + RECOVERY")
    print("COMBAT POLICY UNCHANGED / POLITICA DE COMBATE INALTERADA")
    print("OBSTACLE: two no-motion probes -> temporary block -> next direction")
    return live_v03.main()


if __name__ == "__main__":
    raise SystemExit(main())
