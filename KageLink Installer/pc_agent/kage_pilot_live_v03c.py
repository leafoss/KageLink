from __future__ import annotations

import kage_pilot_live_v03 as live_v03

from pc_agent.kage_pilot.post_combat_v03c import (
    PersistentDojoLeaderDetector,
    PostCombatRecoveryEngineV3,
)


_OriginalObserver = live_v03.ParticleSafeGridTargetObserver
_OriginalVictoryWatcher = live_v03.ChatVictoryWatcher
_ACTIVE_RECOVERY_ENGINE: PostCombatRecoveryEngineV3 | None = None


class AnchorTrackingRecoveryEngine(PostCombatRecoveryEngineV3):
    def __init__(self, *args, **kwargs) -> None:
        global _ACTIVE_RECOVERY_ENGINE
        super().__init__(*args, **kwargs)
        _ACTIVE_RECOVERY_ENGINE = self


class CombatAnchorObserver(_OriginalObserver):
    """Keep the trainer anchor updated without changing any combat decision."""

    def process(self, frame_bgr, *, timestamp=None):
        state = super().process(frame_bgr, timestamp=timestamp)
        engine = _ACTIVE_RECOVERY_ENGINE
        if engine is not None and not engine.post_started:
            engine.observe_world(frame_bgr, state, self, now=state.timestamp)
        return state


class VictoryTransitionWatcher(_OriginalVictoryWatcher):
    def poll(self):
        signal = super().poll()
        if signal is not None and _ACTIVE_RECOVERY_ENGINE is not None:
            # Mark the phase before the first post-combat observer frame so camera flow is never
            # applied twice to the same remembered trainer position.
            _ACTIVE_RECOVERY_ENGINE.begin_post_combat()
        return signal


# The validated combat policy remains unchanged. These replacements add only read-only anchor
# tracking during combat and the safer post-combat return/search state machine.
live_v03.ParticleSafeGridTargetObserver = CombatAnchorObserver
live_v03.ChatVictoryWatcher = VictoryTransitionWatcher
live_v03.DojoLeaderDetector = PersistentDojoLeaderDetector
live_v03.PostCombatRecoveryEngine = AnchorTrackingRecoveryEngine


def main() -> int:
    print("Kage Pilot v0.3c: PERSISTENT DOJO ANCHOR + BOUNDED TRAINER SEARCH")
    print("COMBAT POLICY UNCHANGED / POLITICA DE COMBATE INALTERADA")
    print("RETURN: camera-flow anchor first; expanding-square visual search only as fallback")
    return live_v03.main()


if __name__ == "__main__":
    raise SystemExit(main())
