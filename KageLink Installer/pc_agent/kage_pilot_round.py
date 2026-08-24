"""Canonical isolated Kage Pilot round / Hunting entrypoint.

Dojo remains the default path. Hunting deliberately shares the same packaged helper so
KageLink does not gain another executable or a second combat-core copy.
"""
from __future__ import annotations

import sys


def main() -> int:
    values = list(sys.argv[1:])
    if values and values[0] == "--hunting":
        from pc_agent.kage_pilot.hunting_runtime import main as hunting_main

        sys.argv = [sys.argv[0], *values[1:]]
        return hunting_main()

    from pc_agent.kage_pilot.dojo_combat_runtime import main as dojo_main

    return dojo_main()


if __name__ == "__main__":
    raise SystemExit(main())
