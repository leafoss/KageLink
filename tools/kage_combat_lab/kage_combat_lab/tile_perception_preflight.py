from __future__ import annotations

import json

from .tile_perception import PR24CombatTilePerception


def main() -> int:
    perception = PR24CombatTilePerception()
    print("PR26 TILE PERCEPTION PREFLIGHT: READY")
    print(json.dumps(perception.describe(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
