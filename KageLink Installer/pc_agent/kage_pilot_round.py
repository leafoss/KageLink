"""Canonical isolated Kage Pilot round entrypoint.

The physically validated implementation remains in the historical compatibility
chain until CI and real Windows/BYOND validation authorize its extraction.
"""

from __future__ import annotations

from kage_pilot_live_v03k_round import main


if __name__ == "__main__":
    raise SystemExit(main())
