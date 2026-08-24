"""Canonical isolated Kage Pilot round entrypoint.

Dojo request/spawn/KO/recovery remain supplied by the validated compatibility chain.
Only the combat-action boundary is overlaid by the physically validated Alpha 6 core.
"""

from __future__ import annotations


def main() -> int:
    from pc_agent.kage_pilot.dojo_combat_runtime import main as validated_main

    return validated_main()


if __name__ == "__main__":
    raise SystemExit(main())
