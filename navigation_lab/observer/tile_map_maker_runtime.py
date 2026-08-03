from __future__ import annotations

import argparse
import sys

from ..storage import JsonRepository
from .grid_calibration import GridCalibration
from .scoped_tile_map_maker_window import ScopedTileMapMakerWindow
from .window_capture import WindowsClientCapture


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Semantic Tile MapMaker with a protected HUD learning boundary"
    )
    parser.add_argument("--window-title", default="Shinobi Story Online")
    parser.add_argument("--region-id", default="mapping_input_calibration")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--similarity-threshold", type=float, default=0.92)
    parser.add_argument("--playfield-bottom-ratio", type=float, default=0.75)
    parser.add_argument("--language", choices=["pt-BR", "en-US"], default="pt-BR")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 0.50 <= args.similarity_threshold <= 1.0:
        print("--similarity-threshold must be between 0.50 and 1.0", file=sys.stderr)
        return 2
    if not 0.50 <= args.playfield_bottom_ratio <= 1.0:
        print("--playfield-bottom-ratio must be between 0.50 and 1.0", file=sys.stderr)
        return 2

    try:
        repository = JsonRepository(profile=args.profile)
        if not repository.has_grid_calibration(args.region_id):
            print(
                "No saved grid calibration was found for this profile/region. "
                "Run run_grid_calibration.ps1 first.",
                file=sys.stderr,
            )
            return 5

        calibration = GridCalibration.from_dict(
            repository.load_grid_calibration(args.region_id)
        )
        capture = WindowsClientCapture(args.window_title)
        ScopedTileMapMakerWindow(
            capture=capture,
            repository=repository,
            region_id=args.region_id,
            calibration=calibration,
            similarity_threshold=args.similarity_threshold,
            language=args.language,
            playfield_bottom_ratio=args.playfield_bottom_ratio,
        ).run()
        return 0
    except Exception as exc:
        print(f"Tile MapMaker startup failed: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
