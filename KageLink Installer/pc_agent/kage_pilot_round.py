"""Canonical isolated Kage Pilot round entrypoint.

The physically validated implementation remains in the historical compatibility
chain. KageLink 3.5.1 adds an outer reliability layer for visual position,
relocalization and closed-loop return without changing combat or Trainer matching.
"""

from __future__ import annotations


def main() -> int:
    from kage_pilot_live_v0351_round import main as reliability_main

    return reliability_main()


if __name__ == "__main__":
    raise SystemExit(main())
