from __future__ import annotations

import kage_pilot_live_v03 as live_v03

from pc_agent.kage_pilot.post_combat_v03b import (
    CalibratedDojoLeaderDetector,
    PostCombatRecoveryEngineV2,
)


# The validated combat loop remains untouched. Only the post-combat implementations are
# replaced before main() resolves its module globals.
live_v03.DojoLeaderDetector = CalibratedDojoLeaderDetector
live_v03.PostCombatRecoveryEngine = PostCombatRecoveryEngineV2


def main() -> int:
    print("Kage Pilot v0.3b: LOCAL LEADER TEMPLATE + CAMERA-FLOW MEMORY + CALIBRATED HUD")
    return live_v03.main()


if __name__ == "__main__":
    raise SystemExit(main())
