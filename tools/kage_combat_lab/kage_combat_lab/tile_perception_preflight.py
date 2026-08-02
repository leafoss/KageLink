from .tile_perception import PR24CombatTilePerception


def main() -> int:
    perception = PR24CombatTilePerception()
    print("PR26 TILE PERCEPTION PREFLIGHT: READY")
    print(perception.describe())
    return 0
