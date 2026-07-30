"""Compatibility entry point for the installed KagePilotDojo executable.

The canonical source command is ``kage_pilot.py dojo``. This file remains only
because KageLink 3.5 packages a dedicated helper executable from this path.
"""

from __future__ import annotations

import sys

from kage_pilot import build_parser, resolve_config, run_dojo


def main() -> int:
    return run_dojo(list(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
