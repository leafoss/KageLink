from __future__ import annotations

import kage_pilot_postcombat_live_test_v03c as live_test_v03c

from pc_agent.kage_pilot.post_combat_v03d import PostCombatRecoveryEngineV4


# Reuse the validated isolated input harness and replace only the search/recovery engine.
live_test_v03c.PostCombatRecoveryEngineV3 = PostCombatRecoveryEngineV4


def main() -> int:
    print("Kage Pilot v0.3d CONCENTRIC CELL-RING OFF-SCREEN SEARCH TEST")
    print("RINGS: radius 1 -> 2 -> 3 ...; ARENA CAP: 30x24 cells")
    return live_test_v03c.main()


if __name__ == "__main__":
    raise SystemExit(main())
