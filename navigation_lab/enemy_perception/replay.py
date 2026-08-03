from __future__ import annotations

import argparse
import csv
import json
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay a recorded enemy-perception session")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-zip")
    source.add_argument("--input-session")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--region-id", default="mapping_input_calibration")
    parser.add_argument("--output-session", default="enemy_detection_replay")
    parser.add_argument("--player-anchor-mode", default="Auto")
    parser.add_argument("--player-anchor-x-ratio", type=float, default=0.50)
    parser.add_argument("--player-anchor-y-ratio", type=float, default=0.57)
    parser.add_argument("--semantic-entity-threshold", type=float, default=0.90)
    parser.add_argument("--background-strong-threshold", type=float, default=0.95)
    parser.add_argument("--background-usable-threshold", type=float, default=0.88)
    parser.add_argument("--background-diagnostic-threshold", type=float, default=0.70)
    parser.add_argument("--interest-radius-cells", type=int, default=4)
    parser.add_argument("--debug-mode", choices=("Full", "Balanced", "Off"), default="Balanced")
    parser.add_argument("--debug-stride", type=int, default=5)
    return parser


class RecordedMapper:
    """Rebuild a semantic scan from a prior frame.json plus its raw frame."""

    def __init__(self, frame_payloads: list[dict[str, Any]]) -> None:
        self.payloads = frame_payloads
        self.index = 0

    def process_frame(self, frame: Any):
        from ..observer.continuous_mapping import ContinuousMappingResult
        from ..observer.grid_cells import GridCellCrop
        from ..observer.motion import MotionSample
        from ..observer.tile_knowledge import TileClass, TileClassification
        from ..observer.tile_map_engine import ClassifiedGridCell, TileScanResult

        payload = self.payloads[self.index]
        self.index += 1
        cells = []
        for raw in payload.get("cells", []):
            x0, y0, x1, y1 = [int(value) for value in raw["pixel_bounds"]]
            column, row = [int(value) for value in raw["screen_cell"]]
            category = TileClass(str(raw.get("terrain_class", "unknown")))
            confidence = float(raw.get("terrain_confidence", 0.0))
            known = category != TileClass.UNKNOWN and confidence >= 0.90
            crop = GridCellCrop(
                row,
                column,
                x0,
                y0,
                x1,
                y1,
                frame[y0:y1, x0:x1].copy(),
            )
            cells.append(
                ClassifiedGridCell(
                    crop,
                    TileClassification(category, confidence, known, None),
                )
            )
        state = payload.get("frame_state", {})
        motion = MotionSample(
            float(state.get("camera_dx_px", 0.0)),
            float(state.get("camera_dy_px", 0.0)),
            float(state.get("motion_response", 0.0)),
            bool(state.get("camera_motion_detected", False)),
            "recorded_frame",
        )
        player = payload.get("player", {})
        screen = player.get("screen_cell")
        world = player.get("world_cell")
        return ContinuousMappingResult(
            frame_index=int(payload.get("frame_index", self.index)),
            scan=TileScanResult(frame.copy(), cells),
            player_screen=tuple(screen) if screen is not None else None,
            player_world=tuple(world) if world is not None else None,
            motion=motion,
            mapped_cells=0,
            confirmed_cells=0,
            provisional_cells=0,
            unknown_cells=sum(int(not item.classification.known) for item in cells),
            settled=bool(state.get("settled", True)),
            localization_reason="recorded_session_metadata",
        )


def _find_session_root(path: Path) -> Path:
    if (path / "frames").is_dir():
        return path
    candidates = [
        item
        for item in path.iterdir()
        if item.is_dir() and (item / "frames").is_dir()
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"Could not resolve one recorded session below: {path}")
    return candidates[0]


def _read_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if not path.is_file():
        return summary
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value: Any = row["value"]
            try:
                value = float(value) if "." in str(value) else int(value)
            except ValueError:
                pass
            summary[row["metric"]] = value
    return summary


def _build_engine(
    payloads: list[dict[str, Any]],
    args: argparse.Namespace,
    output_root: Path,
):
    from .background_reference import BackgroundReferenceStore
    from .debug_recorder import DebugRecorder
    from .entity_candidate_validator import EntityCandidateValidator
    from .entity_classifier import EntityClassifier
    from .entity_extractor import EntityExtractor
    from .entity_knowledge import EntityKnowledgeBase
    from .entity_tracker import EntityTracker
    from .hostility_analyzer import HostilityAnalyzer
    from .overlay_detector import OverlayDetector
    from .perception_engine import EnemyPerceptionEngine
    from .player_locator import PlayerLocator
    from .scene_consensus import SceneConsensusLearner

    tile_size = int(payloads[0].get("calibration", {}).get("tile_size_px", 64))
    mapper = RecordedMapper(payloads)
    backgrounds = BackgroundReferenceStore(output_root / "backgrounds")
    recorder = DebugRecorder(
        output_root.parent,
        args.output_session,
        enabled=args.debug_mode.lower() != "off",
        debug_mode=args.debug_mode,
        debug_stride=args.debug_stride,
        async_writes=False,
    )
    knowledge = EntityKnowledgeBase(output_root / "entities")
    return EnemyPerceptionEngine(
        mapper=mapper,
        backgrounds=backgrounds,
        classifier=EntityClassifier(knowledge),
        tracker=EntityTracker(10, interest_radius_cells=args.interest_radius_cells),
        hostility=HostilityAnalyzer(),
        detector=OverlayDetector(24, 0.03, 12),
        extractor=EntityExtractor(tile_size, 12, join_gap_px=1),
        recorder=recorder,
        playfield_bottom_ratio=0.75,
        interest_radius_cells=args.interest_radius_cells,
        processing_radius_cells=args.interest_radius_cells + 1,
        semantic_entity_threshold=args.semantic_entity_threshold,
        background_strong_threshold=args.background_strong_threshold,
        background_usable_threshold=args.background_usable_threshold,
        background_diagnostic_threshold=args.background_diagnostic_threshold,
        candidate_validator=EntityCandidateValidator(
            tile_size,
            args.interest_radius_cells,
        ),
        player_locator=PlayerLocator(
            tile_size,
            10,
            args.player_anchor_mode,
            anchor_x_ratio=args.player_anchor_x_ratio,
            anchor_y_ratio=args.player_anchor_y_ratio,
        ),
        scene_consensus=SceneConsensusLearner(backgrounds, 8, 4, 0.94),
    )


def run_replay(args: argparse.Namespace) -> Path:
    from ..storage.repository import JsonRepository
    import cv2

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.input_zip:
        temporary = tempfile.TemporaryDirectory(prefix="enemy-perception-replay-")
        with zipfile.ZipFile(args.input_zip) as archive:
            archive.extractall(temporary.name)
        input_root = _find_session_root(Path(temporary.name))
    else:
        input_root = _find_session_root(Path(args.input_session))

    frame_dirs = sorted((input_root / "frames").glob("frame_*"))
    payloads = [
        json.loads((directory / "frame.json").read_text(encoding="utf-8"))
        for directory in frame_dirs
    ]
    if not payloads:
        raise RuntimeError(f"No replayable frames were found below: {input_root}")

    repository = JsonRepository(profile=args.profile)
    replay_state_root = (
        repository.root / "enemy_perception_replays" / args.output_session
    )
    engine = _build_engine(payloads, args, replay_state_root)
    source_counts: Counter[str] = Counter()
    background_counts: Counter[str] = Counter()
    track_frames: dict[str, int] = defaultdict(int)
    max_track_distance = 0
    try:
        for directory, payload in zip(frame_dirs, payloads):
            frame = cv2.imread(
                str(directory / "00_raw_window.png"),
                cv2.IMREAD_COLOR,
            )
            if frame is None:
                raise RuntimeError(f"Missing raw frame: {directory}")
            result, _images = engine.process_frame(frame, payload.get("window", {}))
            source_counts[result.player.get("source", "not_found")] += 1
            for cell in result.cells:
                background_counts[cell.background_match_level] += 1
            for entity in result.entities:
                if entity.track_id:
                    track_frames[entity.track_id] += 1
                if entity.distance_to_player is not None:
                    max_track_distance = max(
                        max_track_distance,
                        int(entity.distance_to_player),
                    )
    finally:
        engine.recorder.finalize(engine.tracker.tracks)
        if temporary is not None:
            temporary.cleanup()

    output_session = engine.recorder.session_root
    before = _read_summary(input_root / "summary.csv")
    after = _read_summary(output_session / "summary.csv")
    report = {
        "input_frames": len(frame_dirs),
        "processed_frames": after.get("total_frames", 0),
        "player_visual_frames": source_counts.get("visual_confirmed", 0),
        "player_fallback_frames": source_counts.get(
            "calibrated_anchor_fallback",
            0,
        ),
        "player_temporal_frames": source_counts.get("temporal_predicted", 0),
        "frames_without_player": after.get("frames_without_player", 0),
        "semantic_candidates": after.get("semantic_candidates", 0),
        "residual_candidates": after.get("residual_candidates", 0),
        "entities_created": after.get("entities_created", 0),
        "tracks_created": after.get("tracks_created", 0),
        "track_continuity": max(track_frames.values(), default=0),
        "background_matches_strong": background_counts.get("strong", 0),
        "background_matches_usable": background_counts.get("usable", 0),
        "background_matches_weak": background_counts.get("weak", 0),
        "frames_with_diagnostic_difference": after.get(
            "frames_with_diagnostic_difference",
            0,
        ),
        "possible_enemies": after.get("possible_enemies", 0),
        "probable_enemies": after.get("probable_enemies", 0),
        "confirmed_enemies": after.get("confirmed_enemies", 0),
        "maximum_track_distance": max_track_distance,
        "average_processing_time_ms": after.get("average_processing_time_ms", 0),
        "maximum_processing_time_ms": after.get("maximum_processing_time_ms", 0),
        "disk_usage_bytes": after.get("disk_usage_bytes", 0),
        "before": before,
        "after": after,
    }
    (output_session / "replay_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    with (output_session / "replay_report.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "before", "after"])
        for key in sorted(set(before) | set(after)):
            writer.writerow([key, before.get(key, ""), after.get(key, "")])
    print(f"[Enemy Perception Replay] output={output_session}")
    print(json.dumps(report, indent=2))
    return output_session


def main(argv: list[str] | None = None) -> int:
    run_replay(build_parser().parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
