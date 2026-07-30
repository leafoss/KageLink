"""Canonical Kage Pilot Dojo loop boundary.

The physically validated engine is still implemented by the historical v0.3j
compatibility chain. New integrations must import or execute this versionless
boundary instead of depending on a versioned filename directly.
"""

from __future__ import annotations

from kage_pilot_loop_v03j import main


if __name__ == "__main__":
    raise SystemExit(main())
