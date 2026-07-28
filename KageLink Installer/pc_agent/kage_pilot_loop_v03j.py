from __future__ import annotations

import kage_pilot_loop_v03g as loop_v03g

from pc_agent.kage_pilot.dojo_fight_v03i import request_taijutsu_dojo_spar_single_click


def main() -> int:
    print("Kage Pilot v0.3j: VISUAL MELEE FACING DURING PARTICLE HOLD")
    print("TRAINER: exactly one click; dialog retries never re-click or re-search the trainer")
    print("DIALOG: one initial check + configured retries; failed dialog round does not stop loop")
    print("BURST: only one confirmed adjacent facing pulse; movement and H remain blocked")
    loop_v03g.REQUEST_DOJO_FIGHT = request_taijutsu_dojo_spar_single_click
    loop_v03g.DIALOG_RETRY_POLICY_ENABLED = True
    loop_v03g.ROUND_SCRIPT_NAME = "kage_pilot_live_v03j_round.py"
    return loop_v03g.main()


if __name__ == "__main__":
    raise SystemExit(main())
