from __future__ import annotations

from pathlib import Path

import kage_pilot_loop_v03g as loop_v03g


_REAL_POPEN = loop_v03g.subprocess.Popen


def _visual_round_popen(command, *args, **kwargs):
    rewritten = list(command)
    if len(rewritten) > 1 and Path(str(rewritten[1])).name == "kage_pilot_live_v03g_round.py":
        rewritten[1] = str(Path(__file__).with_name("kage_pilot_live_v03h_round.py"))
    return _REAL_POPEN(rewritten, *args, **kwargs)


def main() -> int:
    print("Kage Pilot v0.3h: combat timeout is only a maximum; chat KO ends combat immediately")
    loop_v03g.subprocess.Popen = _visual_round_popen
    return loop_v03g.main()


if __name__ == "__main__":
    raise SystemExit(main())
