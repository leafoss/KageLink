"""Canonical Kage Pilot Dojo loop boundary.

The physically validated engine is still supplied by the historical compatibility
chain. New integrations, specs and tests must use this versionless module.
"""

from __future__ import annotations

import kage_pilot_loop_v03j as _validated_engine

main = _validated_engine.main
_round_command = _validated_engine._round_command
_run_round_with_ko_buffer = _validated_engine._run_round_with_ko_buffer


if __name__ == "__main__":
    raise SystemExit(main())
