from __future__ import annotations

from pathlib import Path

import kage_pilot_loop_v03g as loop_v03g

from pc_agent.kage_pilot.dojo_fight_v03i import request_taijutsu_dojo_spar_single_click


_REAL_POPEN = loop_v03g.subprocess.Popen


def _v03i_round_popen(command, *args, **kwargs):
    rewritten = list(command)
    if len(rewritten) > 1 and Path(str(rewritten[1])).name == "kage_pilot_live_v03g_round.py":
        rewritten[1] = str(Path(__file__).with_name("kage_pilot_live_v03i_round.py"))
    return _REAL_POPEN(rewritten, *args, **kwargs)


def main() -> int:
    print("Kage Pilot v0.3i: STRICT ONE-CLICK DOJO + MAP-SAVE RESYNC + FAST CHAKRA")
    print("TRAINER: exactly one click, then wait; no automatic second click")
    loop_v03g.request_taijutsu_dojo_spar = request_taijutsu_dojo_spar_single_click
    loop_v03g.subprocess.Popen = _v03i_round_popen
    return loop_v03g.main()


if __name__ == "__main__":
    raise SystemExit(main())
