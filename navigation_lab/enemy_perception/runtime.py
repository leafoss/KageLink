from __future__ import annotations

import argparse
import time
from datetime import datetime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Passive enemy perception debug lab")
    parser.add_argument("--window-title", default="Shinobi Story Online")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--region-id", default="mapping_input_calibration")
    parser.add_argument("--capture-interval", type=float, default=0.20)
    parser.add_argument("--auto-threshold", type=float, default=0.95)
    parser.add_argument("--review-threshold", type=float, default=0.90)
    parser.add_argument("--grouping-threshold", type=float, default=0.965)
    parser.add_argument("--overlay-pixel-threshold", type=int, default=24)
    parser.add_argument("--min-changed-pixel-ratio", type=float, default=0.03)
    parser.add_argument("--min-component-area", type=int, default=12)
    parser.add_argument("--track-ttl-frames", type=int, default=10)
    parser.add_argument("--debug-frames", action="store_true")
    parser.add_argument("--keep-window-visible", action="store_true")
    parser.add_argument("--session-name")
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--max-session-minutes", type=float)
    return parser


def build_engine(args: argparse.Namespace):
    from ..observer.continuous_mapping import ContinuousSemanticMapper
    from ..observer.grid_calibration import GridCalibration
    from ..observer.tile_knowledge import TileKnowledgeBase
    from ..storage.repository import JsonRepository
    from .background_reference import BackgroundReferenceStore
    from .debug_recorder import DebugRecorder
    from .entity_classifier import EntityClassifier
    from .entity_extractor import EntityExtractor
    from .entity_knowledge import EntityKnowledgeBase
    from .entity_tracker import EntityTracker
    from .hostility_analyzer import HostilityAnalyzer
    from .overlay_detector import OverlayDetector
    from .perception_engine import EnemyPerceptionEngine

    repository = JsonRepository(profile=args.profile)
    if not repository.has_grid_calibration(args.region_id):
        raise RuntimeError("A saved grid calibration is required")
    if not repository.has_tile_knowledge(args.region_id):
        raise RuntimeError("Taught tile knowledge is required")

    calibration = GridCalibration.from_dict(
        repository.load_grid_calibration(args.region_id)
    )
    tile_knowledge = TileKnowledgeBase.from_dict(
        repository.load_tile_knowledge(args.region_id)
    )
    mapper = ContinuousSemanticMapper(
        calibration=calibration,
        knowledge=tile_knowledge,
        auto_threshold=args.auto_threshold,
        review_threshold=args.review_threshold,
        grouping_threshold=args.grouping_threshold,
    )
    if repository.has_continuous_mapping(args.region_id):
        mapper.restore_state(repository.load_continuous_mapping(args.region_id))

    session_id = args.session_name or datetime.now().strftime(
        "%Y%m%d_%H%M%S_enemy_lab"
    )
    recorder = DebugRecorder(
        repository.root / "enemy_perception_debug",
        session_id,
        enabled=args.debug_frames,
        max_frames=args.max_frames,
    )
    if args.debug_frames:
        print(f"[Enemy Perception Lab] debug_session={recorder.session_root}", flush=True)
        if not recorder.session_root.is_dir():
            raise RuntimeError(
                f"Debug session directory was not created: {recorder.session_root}"
            )
    else:
        print("[Enemy Perception Lab] debug_session=OFF", flush=True)

    backgrounds = BackgroundReferenceStore(
        repository.root / "enemy_perception" / args.region_id / "backgrounds"
    )
    entity_knowledge = EntityKnowledgeBase(
        repository.root / "enemy_perception" / args.region_id / "entities",
        args.auto_threshold,
        args.review_threshold,
        args.grouping_threshold,
    )
    return EnemyPerceptionEngine(
        mapper=mapper,
        backgrounds=backgrounds,
        classifier=EntityClassifier(entity_knowledge),
        tracker=EntityTracker(args.track_ttl_frames),
        hostility=HostilityAnalyzer(),
        detector=OverlayDetector(
            args.overlay_pixel_threshold,
            args.min_changed_pixel_ratio,
            args.min_component_area,
        ),
        extractor=EntityExtractor(
            calibration.tile_size_px,
            args.min_component_area,
        ),
        recorder=recorder,
        auto_threshold=args.auto_threshold,
        region_id=args.region_id,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = build_engine(args)
    from ..observer.window_capture import WindowsClientCapture

    capture = WindowsClientCapture(args.window_title)
    if args.keep_window_visible:
        from .perception_window import EnemyPerceptionWindow

        EnemyPerceptionWindow(engine, capture, args.capture_interval).run()
        return 0

    started = time.monotonic()
    processed = 0
    try:
        while True:
            if (
                args.max_session_minutes
                and time.monotonic() - started >= args.max_session_minutes * 60
            ):
                break
            frame, bounds = capture.capture()
            engine.process_frame(
                frame,
                {
                    "title": bounds.title,
                    "hwnd": bounds.hwnd,
                    "width": bounds.width,
                    "height": bounds.height,
                    "capture_backend": bounds.capture_backend,
                },
            )
            processed += 1
            if args.max_frames and processed >= args.max_frames:
                break
            time.sleep(args.capture_interval)
    finally:
        engine.recorder.finalize(engine.tracker.tracks)
        capture.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
