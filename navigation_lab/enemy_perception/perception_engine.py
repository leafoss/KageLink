from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .background_reference import BackgroundReferenceStore
from .debug_recorder import DebugRecorder
from .entity_classifier import EntityClassifier
from .entity_extractor import EntityExtractor
from .entity_tracker import EntityTracker
from .hostility_analyzer import HostilityAnalyzer
from .models import (
    CellDebugRecord,
    EntityObservation,
    FramePerception,
    OverlayMetrics,
)
from .overlay_detector import OverlayDetector


TERRAIN_CLASSES = {
    "walkable",
    "wall",
    "walkable_with_jutsu",
    "transition",
    "danger",
}


class EnemyPerceptionEngine:
    """Passive perception layer built on top of the PR 24 continuous semantic mapper."""

    def __init__(
        self,
        mapper: Any,
        backgrounds: BackgroundReferenceStore,
        classifier: EntityClassifier,
        tracker: EntityTracker,
        hostility: HostilityAnalyzer,
        detector: OverlayDetector,
        extractor: EntityExtractor,
        recorder: DebugRecorder | None = None,
        auto_threshold: float = 0.95,
        region_id: str = "mapping_input_calibration",
    ) -> None:
        self.mapper = mapper
        self.backgrounds = backgrounds
        self.classifier = classifier
        self.tracker = tracker
        self.hostility = hostility
        self.detector = detector
        self.extractor = extractor
        self.recorder = recorder
        self.auto_threshold = float(auto_threshold)
        self.region_id = region_id
        self.previous_player_world: tuple[int, int] | None = None

    def process_frame(
        self,
        frame: Any,
        window: dict[str, Any] | None = None,
        attack_detected: bool = False,
        hp_loss_detected: bool = False,
    ) -> tuple[FramePerception, dict[str, Any]]:
        import cv2
        import numpy as np

        started = time.perf_counter()
        mapping = self.mapper.process_frame(frame)
        captured_at = datetime.now(timezone.utc).isoformat()
        events: list[dict[str, Any]] = [
            {"event": "frame_captured", "frame": mapping.frame_index}
        ]
        player_world = mapping.player_world
        player_stationary = (
            self.previous_player_world is not None
            and player_world == self.previous_player_world
            and not mapping.motion.accepted
        )
        player_screen = mapping.player_screen

        cell_records: list[CellDebugRecord] = []
        cell_results: list[tuple[Any, Any, tuple[int, int] | None]] = []
        background_composite = np.zeros_like(frame)
        difference_composite = np.zeros_like(frame)
        mask_composite = np.zeros_like(frame)

        for item in mapping.scan.cells:
            cell = item.crop
            classification = item.classification
            world_cell: tuple[int, int] | None = None
            if player_world is not None and player_screen is not None:
                world_cell = (
                    player_world[0] + cell.column - player_screen[0],
                    player_world[1] + cell.row - player_screen[1],
                )
            terrain_class = classification.category.value
            match = self.backgrounds.choose(world_cell, cell.image)
            decision = "no_reference"
            decision_reason = "background_reference_missing"

            if match.available:
                overlay = self.detector.detect(cell.image, match.image)
                decision = "overlay" if overlay.metrics.overlay_detected else "empty_tile"
                decision_reason = (
                    "difference_threshold_passed"
                    if overlay.metrics.overlay_detected
                    else "matches_empty_reference"
                )
                tile_size = (cell.x1 - cell.x0, cell.y1 - cell.y0)
                background_composite[cell.y0:cell.y1, cell.x0:cell.x1] = cv2.resize(
                    match.image,
                    tile_size,
                    interpolation=cv2.INTER_NEAREST,
                )
                difference_composite[cell.y0:cell.y1, cell.x0:cell.x1] = cv2.resize(
                    overlay.difference,
                    tile_size,
                    interpolation=cv2.INTER_NEAREST,
                )
                mask_composite[cell.y0:cell.y1, cell.x0:cell.x1] = cv2.cvtColor(
                    cv2.resize(
                        overlay.mask,
                        tile_size,
                        interpolation=cv2.INTER_NEAREST,
                    ),
                    cv2.COLOR_GRAY2BGR,
                )
                cell_results.append((cell, overlay, world_cell))
                if overlay.metrics.overlay_detected:
                    events.append(
                        {
                            "event": "overlay_detected",
                            "frame": mapping.frame_index,
                            "screen_cell": [cell.column, cell.row],
                            "world_cell": world_cell,
                        }
                    )
                metrics = overlay.metrics
            else:
                eligible = bool(
                    mapping.settled
                    and classification.known
                    and terrain_class in TERRAIN_CLASSES
                    and classification.confidence >= self.auto_threshold
                    and (cell.column, cell.row) != player_screen
                )
                learned = self.backgrounds.observe_empty_candidate(
                    world_cell,
                    terrain_class,
                    cell.image,
                    eligible,
                )
                if learned:
                    events.append(
                        {
                            "event": "background_reference_learned",
                            "reference_id": learned,
                            "world_cell": world_cell,
                        }
                    )
                metrics = OverlayMetrics()

            cell_records.append(
                CellDebugRecord(
                    screen_cell=(cell.column, cell.row),
                    world_cell=world_cell,
                    pixel_bounds=(cell.x0, cell.y0, cell.x1, cell.y1),
                    terrain_class=terrain_class,
                    terrain_confidence=classification.confidence,
                    background_reference_available=match.available,
                    background_reference_id=match.reference_id,
                    background_reference_confidence=match.confidence,
                    metrics=metrics,
                    decision=decision,
                    decision_reason=decision_reason,
                )
            )

        regions = self.extractor.extract(frame, cell_results)
        observations: list[EntityObservation] = []
        for region in regions:
            feature, classification, group_id = self.classifier.classify(
                region,
                mapping.frame_index,
            )
            observation = EntityObservation(
                region=region,
                feature=feature,
                classification=classification,
                frame_index=mapping.frame_index,
            )
            observations.append(observation)
            if group_id:
                events.append(
                    {
                        "event": "unknown_entity_grouped",
                        "group_id": group_id,
                        "frame": mapping.frame_index,
                    }
                )

        tracking_events, _expired = self.tracker.update(
            observations,
            mapping.frame_index,
            captured_at,
        )
        events.extend(tracking_events)
        for observation in observations:
            track = self.tracker.tracks[observation.track_id]
            events.extend(
                self.hostility.update(
                    track,
                    observation,
                    player_world,
                    player_stationary,
                    mapping.frame_index,
                    attack_detected,
                    hp_loss_detected,
                )
            )

        overlays = self._draw_overlays(
            frame,
            mapping,
            cell_records,
            observations,
        )
        processing_time_ms = (time.perf_counter() - started) * 1000.0
        result = FramePerception(
            session_id=self.recorder.session_id if self.recorder else "runtime",
            frame_index=mapping.frame_index,
            captured_at=captured_at,
            window=window or {},
            calibration={
                "tile_size_px": self.extractor.tile_size_px,
                "region_id": self.region_id,
            },
            frame_state={
                "settled": mapping.settled,
                "camera_motion_detected": mapping.motion.accepted,
                "camera_dx_px": mapping.motion.screen_dx_px,
                "camera_dy_px": mapping.motion.screen_dy_px,
                "motion_response": mapping.motion.response,
                "accepted_for_mapping": mapping.settled,
                "accepted_for_tracking": mapping.settled,
            },
            player={
                "recognized": player_world is not None,
                "screen_cell": list(player_screen) if player_screen else None,
                "world_cell": list(player_world) if player_world else None,
                "confidence": max(
                    (
                        cell.classification.confidence
                        for cell in mapping.scan.cells
                        if cell.classification.category.value == "player"
                    ),
                    default=0.0,
                ),
                "stationary": player_stationary,
            },
            cells=cell_records,
            entities=observations,
            events=events,
            processing_time_ms=processing_time_ms,
        )
        images = {
            "00_raw_window.png": frame,
            "01_grid_overlay.png": overlays[0],
            "02_background_composite.png": background_composite,
            "03_difference_composite.png": difference_composite,
            "04_mask_composite.png": mask_composite,
            "05_components_overlay.png": overlays[1],
            "06_entities_overlay.png": overlays[2],
            "07_tracking_overlay.png": overlays[3],
            "08_hostility_overlay.png": overlays[4],
        }
        if self.recorder:
            self.recorder.record_frame(result, images)
        self.previous_player_world = player_world
        return result, images

    def _draw_overlays(
        self,
        frame: Any,
        mapping: Any,
        cells: list[CellDebugRecord],
        entities: list[EntityObservation],
    ) -> tuple[Any, Any, Any, Any, Any]:
        import cv2

        grid = frame.copy()
        components = frame.copy()
        entity_image = frame.copy()
        tracking = frame.copy()
        hostility = frame.copy()

        for cell in cells:
            x0, y0, x1, y1 = cell.pixel_bounds
            color = (0, 200, 0)
            if cell.metrics.overlay_detected:
                color = (0, 215, 255)
            if not cell.background_reference_available:
                color = (128, 128, 128)
            cv2.rectangle(grid, (x0, y0), (x1 - 1, y1 - 1), color, 1)
            cv2.putText(
                grid,
                f"{cell.screen_cell[0]},{cell.screen_cell[1]}",
                (x0 + 2, y0 + 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.3,
                color,
                1,
            )
            if cell.metrics.overlay_detected:
                cv2.rectangle(
                    components,
                    (x0, y0),
                    (x1 - 1, y1 - 1),
                    (0, 215, 255),
                    2,
                )

        for observation in entities:
            x0, y0, x1, y1 = observation.region.bounding_box_px
            cv2.rectangle(entity_image, (x0, y0), (x1, y1), (0, 215, 255), 2)
            cv2.putText(
                entity_image,
                f"{observation.classification.category.value} {observation.classification.confidence:.2f}",
                (x0, max(12, y0 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 215, 255),
                1,
            )
            cv2.rectangle(tracking, (x0, y0), (x1, y1), (0, 165, 255), 2)
            cv2.putText(
                tracking,
                f"{observation.track_id} d={observation.distance_to_player}",
                (x0, max(12, y0 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 165, 255),
                1,
            )
            color = (0, 0, 255) if observation.hostility_score >= 12 else (0, 165, 255)
            cv2.rectangle(hostility, (x0, y0), (x1, y1), color, 2)
            cv2.putText(
                hostility,
                f"{observation.hostility_state.value} {observation.hostility_score}",
                (x0, max(12, y0 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                color,
                1,
            )
        return grid, components, entity_image, tracking, hostility
