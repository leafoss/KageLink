from __future__ import annotations

import kage_pilot_live_v03 as live_v03
import kage_pilot_live_v03e_round as round_v03e
import kage_pilot_live_v03g_round as round_v03g

from pc_agent.kage_pilot.post_combat_v03h import VisualProgressPostCombatRecoveryEngine


class ActiveVisualProgressRecoveryEngine(VisualProgressPostCombatRecoveryEngine):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        round_v03e._ACTIVE_RECOVERY_ENGINE = self


# Preserve v0.3g robust multi-chat victory and safe R shutdown. Replace only post-combat route
# interpretation so current trainer visuals override false camera-only obstacle readings.
live_v03.PostCombatRecoveryEngine = ActiveVisualProgressRecoveryEngine


def main() -> int:
    print("Kage Pilot v0.3h ROUND: VISUAL-PROGRESS TRAINER RETURN")
    print("COMBAT TIME IS A MAXIMUM TIMEOUT; VICTORY CHAT ENDS IT IMMEDIATELY")
    print("POST: trainer sprite displacement/distance overrides false obstacle blocks")
    return round_v03g.main()


if __name__ == "__main__":
    raise SystemExit(main())
