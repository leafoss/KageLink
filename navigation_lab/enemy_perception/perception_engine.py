from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..observer.playfield_learning_scope import PlayfieldLearningScope
from .background_reference import BackgroundReferenceStore
from .debug_recorder import DebugRecorder
from .entity_candidate_validator import EntityCandidateValidator
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
    """Passive local perception built on PR 24's semantic mapper."""

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
        playfield_bottom_ratio: float = 0.75,
        interest_radius_cells: int = 4,
        background_match_threshold: float = 0.985,
        max_background_changed_ratio: float = 0.65,
        max_background_mean_difference: float = 55.0,
        candidate_validator: EntityCandidateValidator | None = None,
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
        self.playfield_scope = PlayfieldLearningScope(playfield_bottom_ratio)
        self.interest_radius_cells = max(1, int(interest_radius_cells))
        self.processing_radius_cells = self.interest_radius_cells + 1
        self.background_match_threshold = float(background_match_threshold)
        self.max_background_changed_ratio = float(max_background_changed_ratio)
        self.max_background_mean_difference = float(max_background_mean_difference)
        self.candidate_validator = candidate_validator or EntityCandidateValidator(
            tile_size_px=extractor.tile_size_px,
            interest_radius_cells=self.interest_radius_cells,
        )
        self.previous_player_world: tuple[int, int] | None = None
        self._schema_warning_emitted = False

    @staticmethod
    def _manhattan(
        left: tuple[int, int] | None,
        right: tuple[int, int] | None,
    ) -> int | None:
        if left is None or right is None:
            return None
        return abs(left[0] - right[0]) + abs(left[1] - right[1])

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
        if self.backgrounds.outdated_schema_detected and not self._schema_warning_emitted:
            events.append(
                {
                    "event": "background_schema_outdated",
                    "found_schema": self.backgrounds.outdated_schema_version,
                    "expected_schema": 2,
                }
            )
            self._schema_warning_emitted = True

        player_world = mapping.player_world
        player_screen = mapping.player_screen
        player_stationary = (
            self.previous_player_world is not None
            and player_world == self.previous_player_world
            and not mapping.motion.accepted
        )
        frame_height, frame_width = frame.shape[:2]
        playfield_cutoff = self.playfield_scope.cutoff_y(frame_height)

        cell_records: list[CellDebugRecord] = []
        cell_results: list[tuple[Any, Any, tuple[int, int] | None]] = []
        background_composite = cv2.convertScaleAbs(frame, alpha=0.25, beta=0)
        difference_composite = np.zeros_like(frame)
        mask_composite = np.zeros_like(frame)
        candidate_rejections: list[dict[str, Any]] = []
        counters = {
            "total_cells": len(mapping.scan.cells),
            "cells_inside_playfield": 0,
            "cells_inside_processing_roi": 0,
            "background_matches_accepted": 0,
            "background_matches_rejected": 0,
            "raw_components": 0,
            "candidates_rejected": 0,
            "valid_entities": 0,
            "tracks_created": 0,
        }

        for item in mapping.scan.cells:
            cell = item.crop
            classification = item.classification
            screen_cell = (cell.column, cell.row)
            world_cell: tuple[int, int] | None = None
            if player_world is not None and player_screen is not None:
                world_cell = (
                    player_world[0] + cell.column - player_screen[0],
                    player_world[1] + cell.row - player_screen[1],
                )
            terrain_class = classification.category.value
            inside_playfield = self.playfield_scope.is_eligible(item, frame_height)
            screen_distance = self._manhattan(screen_cell, player_screen)
            inside_processing_roi = bool(
                inside_playfield
                and screen_distance is not None
                and screen_distance <= self.processing_radius_cells
            )
            counters["cells_inside_playfield"] += int(inside_playfield)
            counters["cells_inside_processing_roi"] += int(inside_processing_roi)

            match = None
            accepted_match = False
            rejected_reason: str | None = None
            decision = "no_reference"
            decision_reason = "background_reference_missing"
            metrics = OverlayMetrics()

            if not inside_playfield:
                decision = "outside_playfield"
                decision_reason = "hud_excluded"
            elif player_screen is None or player_world is None:
                decision = "no_player_anchor"
                decision_reason = "player_not_recognized"
            elif not inside_processing_roi:
                decision = "outside_interest_radius"
                decision_reason = f"distance_greater_than_{self.processing_radius_cells}"
            elif screen_cell == player_screen:
                decision = "player_cell"
                decision_reason = "player_excluded_from_background_and_entities"
            elif not mapping.settled:
                decision = "moving_frame"
                decision_reason = "frame_not_settled"
            else:
                match_class = terrain_class if terrain_class in TERRAIN_CLASSES else None
                match = self.backgrounds.choose(cell.image, terrain_class=match_class)
                if match.available and match.confidence < self.background_match_threshold:
                    rejected_reason = "background_similarity_below_threshold"
                elif (
                    match.available
                    and terrain_class in TERRAIN_CLASSES
                    and match.terrain_class != terrain_class
                ):
                    rejected_reason = "background_terrain_class_mismatch"
                elif match.available:
                    overlay = self.detector.detect(cell.image, match.image)
                    metrics = overlay.metrics
                    structural = bool(
                        metrics.changed_pixel_ratio >= self.max_background_changed_ratio
                        or metrics.difference_mean >= self.max_background_mean_difference
                    )
                    if structural:
                        rejected_reason = "structural_background_mismatch"
                        events.append(
                            {
                                "event": "structural_background_mismatch",
                                "frame": mapping.frame_index,
                                "screen_cell": list(screen_cell),
                                "changed_pixel_ratio": metrics.changed_pixel_ratio,
                                "difference_mean": metrics.difference_mean,
                            }
                        )
                    else:
                        accepted_match = True
                        counters["background_matches_accepted"] += 1
                        decision = "overlay" if metrics.overlay_detected else "empty_tile"
                        decision_reason = (
                            "difference_threshold_passed"
                            if metrics.overlay_detected
                            else "matches_known_empty_appearance"
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
                        if metrics.overlay_detected:
                            cell_results.append((cell, overlay, world_cell))
                            events.append(
                                {
                                    "event": "overlay_detected",
                                    "frame": mapping.frame_index,
                                    "screen_cell": list(screen_cell),
                                    "world_cell": world_cell,
                                    "background_reference_id": match.reference_id,
                                    "background_similarity": match.confidence,
                                }
                            )

                if rejected_reason:
                    counters["background_matches_rejected"] += 1
                    decision = "no_reference"
                    decision_reason = rejected_reason
                    events.append(
                        {
                            "event": "background_reference_rejected",
                            "frame": mapping.frame_index,
                            "screen_cell": list(screen_cell),
                            "reference_id": match.reference_id if match else None,
                            "confidence": match.confidence if match else 0.0,
                            "reason": rejected_reason,
                        }
                    )

                if not accepted_match and rejected_reason != "structural_background_mismatch":
                    eligible = bool(
                        classification.known
                        and terrain_class in TERRAIN_CLASSES
                        and classification.confidence >= self.auto_threshold
                    )
                    learned = self.backgrounds.observe_empty_candidate(
                        world_cell,
                        terrain_class,
                        cell.image,
                        eligible,
                        source_frame=mapping.frame_index,
                    )
                    if learned:
                        events.append(
                            {
                                "event": "background_reference_learned",
                                "reference_id": learned,
                                "source_world_cell": world_cell,
                                "terrain_class": terrain_class,
                            }
                        )

            if accepted_match and match is not None:
                cv2.putText(
                    background_composite,
                    f"REF {match.confidence:.0%}",
                    (cell.x0 + 2, min(cell.y1 - 3, cell.y0 + 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.30,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
            elif inside_playfield and inside_processing_roi:
                label = "REF REJECTED" if rejected_reason else "NO REF"
                cv2.putText(
                    background_composite,
                    label,
                    (cell.x0 + 2, min(cell.y1 - 3, cell.y0 + 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.27,
                    (180, 180, 180),
                    1,
                    cv2.LINE_AA,
                )

            cell_records.append(
                CellDebugRecord(
                    screen_cell=screen_cell,
                    world_cell=world_cell,
                    pixel_bounds=(cell.x0, cell.y0, cell.x1, cell.y1),
                    terrain_class=terrain_class,
                    terrain_confidence=classification.confidence,
                    background_reference_available=accepted_match,
                    background_reference_id=(match.reference_id if match else None),
                    background_reference_confidence=(match.confidence if match else 0.0),
                    metrics=metrics,
                    decision=decision,
                    decision_reason=decision_reason,
                    inside_playfield=inside_playfield,
                    inside_processing_roi=inside_processing_roi,
                    background_reference_rejected=bool(rejected_reason),
                    background_reference_rejection_reason=rejected_reason,
                    background_reference_terrain_class=(match.terrain_class if match else None),
                    background_reference_source_world_cell=(
                        match.source_world_cell if match else None
                    ),
                )
            )

        raw_regions = self.extractor.extract(frame, cell_results)
        counters["raw_components"] = len(raw_regions)
        valid_regions: list[Any] = []
        rejected_regions: list[tuple[Any, Any]] = []
        for region in raw_regions:
            validation = self.candidate_validator.validate(
                region,
                player_world,
                playfield_cutoff,
            )
            if not validation.valid:
                rejected_regions.append((region, validation))
                rejection = validation.to_dict(region)
                candidate_rejections.append(rejection)
                counters["candidates_rejected"] += 1
                events.append(
                    {
                        "event": "component_rejected",
                        "frame": mapping.frame_index,
                        **rejection,
                    }
                )
                continue
            valid_regions.append((region, validation))

        observations: list[EntityObservation] = []
        for region, validation in valid_regions:
            feature, classification, group_id = self.classifier.classify(
                region,
                mapping.frame_index,
            )
            observation = EntityObservation(
                region=region,
                feature=feature,
                classification=classification,
                frame_index=mapping.frame_index,
                distance_to_player=validation.distance_to_player,
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
            player_world=player_world,
        )
        events.extend(tracking_events)
        counters["tracks_created"] = sum(
            int(event.get("event") == "entity_created") for event in tracking_events
        )
        tracked_observations = [item for item in observations if item.track_id]
        counters["valid_entities"] = len(tracked_observations)
        for observation in tracked_observations:
            track = self.tracker.tracks.get(observation.track_id)
            if track is None:
                continue
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
            raw_regions,
            rejected_regions,
            tracked_observations,
            playfield_cutoff,
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
            entities=tracked_observations,
            events=events,
            processing_time_ms=processing_time_ms,
            playfield={
                "bottom_ratio": self.playfield_scope.bottom_ratio,
                "cutoff_y_px": playfield_cutoff,
            },
            roi={
                "interest_radius_cells": self.interest_radius_cells,
                "processing_radius_cells": self.processing_radius_cells,
                "distance_metric": "manhattan",
            },
            counters=counters,
            candidate_rejections=candidate_rejections,
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
        raw_regions: list[Any],
        rejected_regions: list[tuple[Any, Any]],
        entities: list[EntityObservation],
        playfield_cutoff: int,
    ) -> tuple[Any, Any, Any, Any, Any]:
        import cv2
        import numpy as np

        grid = frame.copy()
        components = frame.copy()
        entity_image = frame.copy()
        tracking = frame.copy()
        hostility = frame.copy()
        height, width = frame.shape[:2]

        for image in (grid, components, entity_image, tracking, hostility):
            shade = image.copy()
            cv2.rectangle(shade, (0, playfield_cutoff), (width - 1, height - 1), (25, 25, 25), -1)
            cv2.addWeighted(shade, 0.65, image, 0.35, 0.0, image)
            cv2.line(image, (0, playfield_cutoff), (width - 1, playfield_cutoff), (0, 0, 255), 2)

        for cell in cells:
            x0, y0, x1, y1 = cell.pixel_bounds
            if not cell.inside_playfield:
                color = (60, 60, 60)
            elif not cell.inside_processing_roi:
                color = (80, 80, 80)
            elif cell.background_reference_rejected:
                color = (80, 80, 220)
            elif not cell.background_reference_available:
                color = (128, 128, 128)
            elif cell.metrics.overlay_detected:
                color = (0, 215, 255)
            else:
                color = (0, 200, 0)
            cv2.rectangle(grid, (x0, y0), (x1 - 1, y1 - 1), color, 1)
            if cell.inside_processing_roi:
                cv2.putText(
                    grid,
                    f"{cell.screen_cell[0]},{cell.screen_cell[1]}",
                    (x0 + 2, y0 + 12),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.3,
                    color,
                    1,
                )

        for region in raw_regions:
            x0, y0, x1, y1 = region.bounding_box_px
            cv2.rectangle(components, (x0, y0), (x1, y1), (0, 215, 255), 1)
        for region, validation in rejected_regions:
            x0, y0, x1, y1 = region.bounding_box_px
            cv2.rectangle(components, (x0, y0), (x1, y1), (150, 150, 150), 2)
            cv2.putText(
                components,
                validation.reason[:24],
                (x0, max(12, y0 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.36,
                (210, 210, 210),
                1,
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
                f"{observation.track_id} D={observation.distance_to_player}",
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

        if mapping.player_screen is not None:
            player_column, player_row = mapping.player_screen
            tile = self.extractor.tile_size_px
            center_x = player_column * tile + tile // 2
            center_y = player_row * tile + tile // 2
            radius_px = self.interest_radius_cells * tile
            points = np.array(
                [
                    [center_x, center_y - radius_px],
                    [center_x + radius_px, center_y],
                    [center_x, center_y + radius_px],
                    [center_x - radius_px, center_y],
                ],
                np.int32,
            )
            for image in (grid, tracking, hostility):
                cv2.polylines(image, [points], True, (255, 180, 0), 2)
                cv2.putText(
                    image,
                    f"PLAYER ROI D<={self.interest_radius_cells}",
                    (max(0, center_x - 80), max(16, center_y - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (255, 180, 0),
                    1,
                )
        return grid, components, entity_image, tracking, hostility
