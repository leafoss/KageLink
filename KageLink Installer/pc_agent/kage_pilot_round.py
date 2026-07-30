"""Canonical isolated Kage Pilot round entrypoint.

The physically validated implementation remains in the historical compatibility
chain until CI and real Windows/BYOND validation authorize its extraction.
Importing this boundary must not install runtime monkeypatches; the engine is
loaded only when the isolated round is actually executed.
"""

from __future__ import annotations


def main() -> int:
    from kage_pilot_live_v03k_round import main as validated_main

    return validated_main()


if __name__ == "__main__":
    raise SystemExit(main())
