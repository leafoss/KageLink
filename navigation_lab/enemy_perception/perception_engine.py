from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..observer.playfield_learning_scope import PlayfieldLearningScope
from .background_reference import BackgroundReferenceStore
from .debug_recorder import DebugRecorder
from .entity_candidate_fusion import EntityCandidateFusion
from .entity_candidate_validator import EntityCandidateValidator
from .entity_classifier import EntityClassifier
from .entity_extractor import EntityExtractor
from .entity_tracker import EntityTracker
from .hostility_analyzer import HostilityAnalyzer
from .models import (
    BackgroundMatchLevel,
    CandidateSource,
    CellDebugRecord,
    EntityClass,
    EntityClassification,
    EntityObservation,
    EntityRegion,
    FramePerception,
    OverlayMetrics,
)
from .overlay_detector import OverlayDetector
from .player_locator import PlayerLocator
from .scene_consensus import SceneConsensusLearner


TERRAIN_CLASSES = {
    "walkable",
    "wall",
    "walkable_with_jutsu",
    "transition",
    "danger",
}


class EnemyPerceptionEngine:
    """Passive local perception built on PR 24's semantic mapper.

    Two independent paths feed the tracker:
    1. semantic NPC candidates, which never require a background;
    2. residual foreground candidates over a usable empty-tile appearance.
    """

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
        processing_radius_cells: int | None = None,
        semantic_entity_threshold: float = 0.90,
        background_strong_threshold: float = 0.95,
        background_usable_threshold: float = 0.88,
        background_diagnostic_threshold: float = 0.70,
        max_background_changed_ratio: float = 0.65,
        max_background_mean_difference: float = 55.0,
        candidate_validator: EntityCandidateValidator | None = None,
        player_locator: PlayerLocator | None = None,
        fusion: EntityCandidateFusion | None = None,
        scene_consensus: SceneConsensusLearner | None = None,
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
        self.processing_radius_cells = max(
            self.interest_radius_cells,
            int(processing_radius_cells or (self.interest_radius_cells + 1)),
        )
        self.semantic_entity_threshold = float(semantic_entity_threshold)
        self.background_strong_threshold = float(background_strong_threshold)
        self.background_usable_threshold = float(background_usable_threshold)
        self.background_diagnostic_threshold = float(background_diagnostic_threshold)
        if not (
            0.0
            <= self.background_diagnostic_threshold
            <= self.background_usable_threshold
            <= self.background_strong_threshold
            <= 1.0
        ):
            raise ValueError("background thresholds must satisfy diagnostic <= usable <= strong")
        self.max_background_changed_ratio = float(max_background_changed_ratio)
        self.max_background_mean_difference = float(max_background_mean_difference)
        self.candidate_validator = candidate_validator or EntityCandidateValidator(
            tile_size_px=extractor.tile_size_px,
            interest_radius_cells=self.interest_radius_cells,
        )
        self.player_locator = player_locator or PlayerLocator(
            tile_size_px=extractor.tile_size_px,
        )
        self.fusion = fusion or EntityCandidateFusion()
        self.scene_consensus = scene_consensus or SceneConsensusLearner(backgrounds)
        self.previous_player_world: tuple[int, int] | None = None
        self.previous_player_source: str | None = None
        self._schema_warning_emitted = False

    @staticmethod
    def _manhattan(
        left: tuple[int, int] | None,
        right: tuple[int, int] | None,
    ) -> int | None:
        if left is None or right is None:
            return None
        return abs(left[0] - right[0]) + abs(left[1] - right[1])

    def _match_level(self, score: float) -> BackgroundMatchLevel:
        if score >= self.background_strong_threshold:
            return BackgroundMatchLevel.STRONG
        if score >= self.background_usable_threshold:
            return BackgroundMatchLevel.USABLE
        if score >= self.background_diagnostic_threshold:
            return BackgroundMatchLevel.WEAK
        return BackgroundMatchLevel.NONE

    def _world_cell(
        self,
        column: int,
        row: int,
        player_screen: tuple[int, int] | None,
        player_world: tuple[int, int] | None,
    ) -> tuple[int, int] | None:
        if player_screen is None or player_world is None:
            return None
        return (
            player_world[0] + int(column) - player_screen[0],
            player_world[1] + int(row) - player_screen[1],
        )

    def _semantic_observations(
        self,
        frame: Any,
        semantic_cells: list[Any],
        player_screen: tuple[int, int] | None,
        player_world: tuple[int, int] | None,
        frame_index: int,
        background_by_cell: dict[tuple[int, int], dict[str, Any]],
    ) -> tuple[list[EntityObservation], list[dict[str, Any]]]:
        import numpy as np

        observations: list[EntityObservation] = []
        rejections: list[dict[str, Any]] = []
        remaining = {(item.crop.column, item.crop.row): item for item in semantic_cells}
        while remaining:
            key, first = remaining.popitem()
            group = [first]
            frontier = [key]
            while frontier:
                column, row = frontier.pop()
                for neighbor in (
                    (column + 1, row),
                    (column - 1, row),
                    (column, row + 1),
                    (column, row - 1),
                ):
                    item = remaining.pop(neighbor, None)
                    if item is not None:
                        group.append(item)
                        frontier.append(neighbor)
            cells = [item.crop for item in group]
            x0 = min(cell.x0 for cell in cells)
            y0 = min(cell.y0 for cell in cells)
            x1 = max(cell.x1 for cell in cells)
            y1 = max(cell.y1 for cell in cells)
            anchor_cell = max(cells, key=lambda cell: (cell.row, -abs(cell.column - sum(c.column for c in cells) / len(cells))))
            anchor_screen = (anchor_cell.column, anchor_cell.row)
            anchor_world = self._world_cell(
                anchor_cell.column,
                anchor_cell.row,
                player_screen,
                player_world,
            )
            crop = frame[y0:y1, x0:x1].copy()
            mask = np.full(crop.shape[:2], 255, np.uint8)
            region = EntityRegion(
                bounding_box_px=(x0, y0, x1, y1),
                anchor_screen_cell=anchor_screen,
                anchor_world_cell=anchor_world,
                covered_cells=[(cell.column, cell.row) for cell in cells],
                crop=crop,
                mask=mask,
                difference=crop.copy(),
            )
            validation = self.candidate_validator.validate(
                region,
                player_world,
                self._current_playfield_cutoff,
            )
            if not validation.valid:
                rejections.append(validation.to_dict(region))
                continue
            confidence = max(float(item.classification.confidence) for item in group)
            matched = max(group, key=lambda item: item.classification.confidence).classification.matched_example_id
            classification = EntityClassification(
                EntityClass.NEUTRAL_NPC,
                confidence,
                True,
                matched,
            )
            feature = self.classifier.knowledge.extractor.extract(region.crop, region.mask)
            bg = background_by_cell.get(anchor_screen, {})
            observations.append(
                EntityObservation(
                    region=region,
                    feature=feature,
                    classification=classification,
                    frame_index=frame_index,
                    distance_to_player=validation.distance_to_player,
                    candidate_sources=[CandidateSource.SEMANTIC_NPC.value],
                    semantic_class="npc",
                    semantic_confidence=confidence,
                    background_cluster_id=bg.get("cluster_id"),
                    background_confidence=float(bg.get("score", 0.0)),
                    background_match_level=str(bg.get("level", BackgroundMatchLevel.NONE.value)),
                    overall_candidate_confidence=confidence,
                )
            )
        return observations, rejections

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
        frame_height, frame_width = frame.shape[:2]
        playfield_cutoff = self.playfield_scope.cutoff_y(frame_height)
        self._current_playfield_cutoff = playfield_cutoff
        player_location = self.player_locator.locate(
            mapping,
            frame_width,
            playfield_cutoff,
        )
        player_world = player_location.world_cell
        player_screen = player_location.screen_cell
        player_stationary = (
            self.previous_player_world is not None
            and player_world == self.previous_player_world
            and not mapping.motion.accepted
        )

        events: list[dict[str, Any]] = [
            {"event": "frame_captured", "frame": mapping.frame_index}
        ]
        if player_location.source.value != self.previous_player_source:
            events.append(
                {
                    "event": "player_source_changed",
                    "frame": mapping.frame_index,
                    "from": self.previous_player_source,
                    "to": player_location.source.value,
                }
            )
        if not player_location.recognized:
            events.append({"event": "player_lost", "frame": mapping.frame_index})
        if self.backgrounds.outdated_schema_detected and not self._schema_warning_emitted:
            events.append(
                {
                    "event": "background_schema_outdated",
                    "found_schema": self.backgrounds.outdated_schema_version,
                    "expected_schema": 3,
                }
            )
            self._schema_warning_emitted = True

        cell_records: list[CellDebugRecord] = []
        record_by_screen: dict[tuple[int, int], CellDebugRecord] = {}
        residual_cell_results: list[tuple[Any, Any, tuple[int, int] | None]] = []
        semantic_cells: list[Any] = []
        consensus_candidates: list[tuple[str, Any]] = []
        background_by_cell: dict[tuple[int, int], dict[str, Any]] = {}

        background_composite = cv2.convertScaleAbs(frame, alpha=0.25, beta=0)
        difference_composite = np.zeros_like(frame)
        mask_composite = np.zeros_like(frame)
        candidate_rejections: list[dict[str, Any]] = []
        counters = {
            "total_cells": len(mapping.scan.cells),
            "cells_inside_playfield": 0,
            "cells_inside_processing_roi": 0,
            "background_matches_strong": 0,
            "background_matches_usable": 0,
            "background_matches_weak": 0,
            "background_matches_rejected": 0,
            "diagnostic_differences": 0,
            "operational_differences": 0,
            "semantic_candidates": 0,
            "residual_candidates": 0,
            "fused_candidates": 0,
            "raw_components": 0,
            "candidates_rejected": 0,
            "valid_entities": 0,
            "tracks_created": 0,
        }

        for item in mapping.scan.cells:
            cell = item.crop
            classification = item.classification
            screen_cell = (cell.column, cell.row)
            world_cell = self._world_cell(
                cell.column,
                cell.row,
                player_screen,
                player_world,
            )
            semantic_class = classification.category.value
            inside_playfield = self.playfield_scope.is_eligible(item, frame_height)
            screen_distance = self._manhattan(screen_cell, player_screen)
            inside_processing_roi = bool(
                inside_playfield
                and screen_distance is not None
                and screen_distance <= self.processing_radius_cells
            )
            counters["cells_inside_playfield"] += int(inside_playfield)
            counters["cells_inside_processing_roi"] += int(inside_processing_roi)

            is_player_cell = bool(player_screen is not None and screen_cell == player_screen)
            is_semantic_npc = bool(
                classification.known
                and semantic_class == "npc"
                and classification.confidence >= self.semantic_entity_threshold
                and inside_playfield
                and screen_distance is not None
                and screen_distance <= self.interest_radius_cells
                and not is_player_cell
            )
            if is_semantic_npc:
                semantic_cells.append(item)

            if (
                mapping.settled
                and inside_playfield
                and semantic_class in TERRAIN_CLASSES
                and classification.known
                and not is_player_cell
            ):
                consensus_candidates.append((semantic_class, cell.image))

            match = None
            level = BackgroundMatchLevel.NONE
            metrics = OverlayMetrics()
            diagnostic_generated = False
            operational_allowed = False
            rejected_reason: str | None = None
            decision = "no_reference"
            decision_reason = "background_reference_missing"

            if not inside_playfield:
                decision = "outside_playfield"
                decision_reason = "hud_excluded"
            elif not player_location.recognized:
                decision = "no_player_anchor"
                decision_reason = "player_not_located"
            elif not inside_processing_roi:
                decision = "outside_interest_radius"
                decision_reason = f"distance_greater_than_{self.processing_radius_cells}"
            elif is_player_cell:
                decision = "player_cell"
                decision_reason = f"player_{player_location.source.value}"
            elif not mapping.settled:
                decision = "moving_frame"
                decision_reason = "frame_not_settled"
            else:
                match_class = semantic_class if semantic_class in TERRAIN_CLASSES else None
                match = self.backgrounds.choose(cell.image, terrain_class=match_class)
                if match.available:
                    level = self._match_level(match.confidence)
                    match.match_level = level
                    background_by_cell[screen_cell] = {
                        "cluster_id": match.cluster_id,
                        "score": match.confidence,
                        "level": level.value,
                    }
                    tile_size = (cell.x1 - cell.x0, cell.y1 - cell.y0)
                    background_composite[cell.y0:cell.y1, cell.x0:cell.x1] = cv2.resize(
                        match.image,
                        tile_size,
                        interpolation=cv2.INTER_NEAREST,
                    )
                    if level != BackgroundMatchLevel.NONE:
                        overlay = self.detector.detect(cell.image, match.image)
                        metrics = overlay.metrics
                        diagnostic_generated = True
                        counters["diagnostic_differences"] += 1
                        difference = cv2.resize(
                            overlay.difference,
                            tile_size,
                            interpolation=cv2.INTER_NEAREST,
                        )
                        if level == BackgroundMatchLevel.WEAK:
                            yellow = np.zeros_like(difference)
                            yellow[:, :, 1] = difference.max(axis=2)
                            yellow[:, :, 2] = difference.max(axis=2)
                            difference = yellow
                        difference_composite[cell.y0:cell.y1, cell.x0:cell.x1] = difference
                        mask = cv2.resize(
                            overlay.mask,
                            tile_size,
                            interpolation=cv2.INTER_NEAREST,
                        )
                        structural = bool(
                            metrics.changed_pixel_ratio >= self.max_background_changed_ratio
                            or metrics.difference_mean >= self.max_background_mean_difference
                        )
                        operational_allowed = bool(
                            level in {BackgroundMatchLevel.STRONG, BackgroundMatchLevel.USABLE}
                            and not structural
                        )
                        if operational_allowed:
                            counters["operational_differences"] += 1
                            mask_composite[cell.y0:cell.y1, cell.x0:cell.x1] = cv2.cvtColor(
                                mask,
                                cv2.COLOR_GRAY2BGR,
                            )
                            decision = "overlay" if metrics.overlay_detected else "empty_tile"
                            decision_reason = (
                                "operational_residual_detected"
                                if metrics.overlay_detected
                                else "matches_known_empty_appearance"
                            )
                            if metrics.overlay_detected:
                                residual_cell_results.append((cell, overlay, world_cell))
                        elif structural:
                            rejected_reason = "structural_background_mismatch"
                            decision = "diagnostic_only"
                            decision_reason = rejected_reason
                            events.append(
                                {
                                    "event": "structural_mismatch",
                                    "frame": mapping.frame_index,
                                    "screen_cell": list(screen_cell),
                                    "score": match.confidence,
                                }
                            )
                        else:
                            decision = "diagnostic_only"
                            decision_reason = f"background_{level.value}_debug_only"
                    else:
                        rejected_reason = "background_below_diagnostic_threshold"
                        decision = "no_reference"
                        decision_reason = rejected_reason
                else:
                    decision_reason = "no_visual_background_candidate"

            if level == BackgroundMatchLevel.STRONG:
                counters["background_matches_strong"] += 1
            elif level == BackgroundMatchLevel.USABLE:
                counters["background_matches_usable"] += 1
            elif level == BackgroundMatchLevel.WEAK:
                counters["background_matches_weak"] += 1
            elif match is not None and match.available:
                counters["background_matches_rejected"] += 1

            if match is not None and match.available:
                label = f"{level.value.upper()} {match.confidence:.0%}"
                cv2.putText(
                    background_composite,
                    label,
                    (cell.x0 + 2, min(cell.y1 - 3, cell.y0 + 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.27,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
            elif inside_playfield and inside_processing_roi:
                cv2.putText(
                    background_composite,
                    "NO REF",
                    (cell.x0 + 2, min(cell.y1 - 3, cell.y0 + 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.27,
                    (180, 180, 180),
                    1,
                    cv2.LINE_AA,
                )

            record = CellDebugRecord(
                screen_cell=screen_cell,
                world_cell=world_cell,
                pixel_bounds=(cell.x0, cell.y0, cell.x1, cell.y1),
                terrain_class=semantic_class,
                terrain_confidence=classification.confidence,
                background_reference_available=operational_allowed,
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
                background_reference_source_world_cell=(match.source_world_cell if match else None),
                player_location_source=player_location.source.value,
                best_background_cluster_id=(match.cluster_id if match else None),
                best_background_score=(match.confidence if match else 0.0),
                background_match_level=level.value,
                diagnostic_difference_generated=diagnostic_generated,
                operational_difference_allowed=operational_allowed,
                semantic_candidate_created=is_semantic_npc,
                residual_candidate_created=bool(operational_allowed and metrics.overlay_detected),
            )
            cell_records.append(record)
            record_by_screen[screen_cell] = record

        learned = self.scene_consensus.observe(
            consensus_candidates,
            mapping.frame_index,
        )
        for reference_id in learned:
            events.append(
                {
                    "event": "background_cluster_created",
                    "frame": mapping.frame_index,
                    "reference_id": reference_id,
                    "source": "scene_consensus",
                }
            )

        semantic_observations, semantic_rejections = self._semantic_observations(
            frame,
            semantic_cells,
            player_screen,
            player_world,
            mapping.frame_index,
            background_by_cell,
        )
        counters["semantic_candidates"] = len(semantic_observations)
        for item in semantic_observations:
            events.append(
                {
                    "event": "semantic_entity_detected",
                    "frame": mapping.frame_index,
                    "semantic_class": item.semantic_class,
                    "confidence": item.semantic_confidence,
                    "anchor_world_cell": item.region.anchor_world_cell,
                    "distance": item.distance_to_player,
                }
            )
        candidate_rejections.extend(semantic_rejections)

        raw_regions = self.extractor.extract(frame, residual_cell_results)
        counters["raw_components"] = len(raw_regions)
        residual_observations: list[EntityObservation] = []
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
                events.append({"event": "component_rejected", "frame": mapping.frame_index, **rejection})
                continue
            feature, classification, group_id = self.classifier.classify(
                region,
                mapping.frame_index,
            )
            record = record_by_screen.get(region.anchor_screen_cell)
            observation = EntityObservation(
                region=region,
                feature=feature,
                classification=classification,
                frame_index=mapping.frame_index,
                distance_to_player=validation.distance_to_player,
                candidate_sources=[CandidateSource.BACKGROUND_RESIDUAL.value],
                semantic_class=None,
                semantic_confidence=0.0,
                background_cluster_id=(record.best_background_cluster_id if record else None),
                background_confidence=(record.best_background_score if record else 0.0),
                background_match_level=(record.background_match_level if record else BackgroundMatchLevel.NONE.value),
                overall_candidate_confidence=max(
                    classification.confidence,
                    record.best_background_score if record else 0.0,
                ),
            )
            residual_observations.append(observation)
            events.append(
                {
                    "event": "residual_entity_detected",
                    "frame": mapping.frame_index,
                    "anchor_world_cell": region.anchor_world_cell,
                    "distance": validation.distance_to_player,
                }
            )
            if group_id:
                events.append(
                    {
                        "event": "unknown_entity_grouped",
                        "group_id": group_id,
                        "frame": mapping.frame_index,
                    }
                )
        counters["residual_candidates"] = len(residual_observations)
        counters["candidates_rejected"] = len(candidate_rejections)

        observations = self.fusion.fuse(
            semantic_observations,
            residual_observations,
        )
        counters["fused_candidates"] = len(observations)
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
            semantic_observations,
            raw_regions,
            rejected_regions,
            tracked_observations,
            playfield_cutoff,
            player_location,
        )
        processing_time_ms = (time.perf_counter() - started) * 1000.0
        player_payload = player_location.to_dict()
        player_payload["stationary"] = player_stationary
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
            player=player_payload,
            player_location=player_payload,
            background={
                "clusters_available": self.backgrounds.cluster_count,
                "scene_consensus_clusters": sum(
                    int(cluster.source == "scene_consensus")
                    for bucket in self.backgrounds.clusters_by_class.values()
                    for cluster in bucket
                ),
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
        self.previous_player_source = player_location.source.value
        return result, images

    def _draw_overlays(
        self,
        frame: Any,
        mapping: Any,
        cells: list[CellDebugRecord],
        semantic_entities: list[EntityObservation],
        raw_regions: list[Any],
        rejected_regions: list[tuple[Any, Any]],
        entities: list[EntityObservation],
        playfield_cutoff: int,
        player_location: Any,
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
            elif cell.semantic_candidate_created:
                color = (255, 0, 255)
            elif cell.background_match_level == BackgroundMatchLevel.STRONG.value:
                color = (0, 200, 0)
            elif cell.background_match_level == BackgroundMatchLevel.USABLE.value:
                color = (0, 215, 255)
            elif cell.background_match_level == BackgroundMatchLevel.WEAK.value:
                color = (0, 255, 255)
            else:
                color = (128, 128, 128)
            cv2.rectangle(grid, (x0, y0), (x1 - 1, y1 - 1), color, 1)
            labels: list[str] = []
            if cell.semantic_candidate_created:
                labels.append(f"NPC {cell.terrain_confidence:.0%}")
            if cell.diagnostic_difference_generated:
                labels.append(f"BG {cell.background_match_level.upper()} {cell.best_background_score:.0%}")
            if labels:
                cv2.putText(
                    grid,
                    " | ".join(labels),
                    (x0 + 2, min(y1 - 3, y0 + 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.28,
                    color,
                    1,
                )

        for observation in semantic_entities:
            x0, y0, x1, y1 = observation.region.bounding_box_px
            cv2.rectangle(components, (x0, y0), (x1, y1), (255, 0, 255), 2)
            cv2.putText(
                components,
                f"SEMANTIC NPC {observation.semantic_confidence:.0%}",
                (x0, max(12, y0 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.36,
                (255, 0, 255),
                1,
            )
        for region in raw_regions:
            x0, y0, x1, y1 = region.bounding_box_px
            cv2.rectangle(components, (x0, y0), (x1, y1), (0, 215, 255), 1)
            cv2.putText(components, "RESIDUAL", (x0, max(12, y0 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (0, 215, 255), 1)
        for region, validation in rejected_regions:
            x0, y0, x1, y1 = region.bounding_box_px
            cv2.rectangle(components, (x0, y0), (x1, y1), (150, 150, 150), 2)
            cv2.putText(components, validation.reason[:24], (x0, max(12, y0 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (210, 210, 210), 1)

        for observation in entities:
            x0, y0, x1, y1 = observation.region.bounding_box_px
            source = "+".join(observation.candidate_sources) or "unknown"
            cv2.rectangle(entity_image, (x0, y0), (x1, y1), (0, 215, 255), 2)
            cv2.putText(entity_image, source, (x0, max(12, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 215, 255), 1)
            cv2.rectangle(tracking, (x0, y0), (x1, y1), (0, 165, 255), 2)
            cv2.putText(
                tracking,
                f"{observation.track_id} D={observation.distance_to_player} {observation.movement_state}",
                (x0, max(12, y0 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
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
                0.36,
                color,
                1,
            )

        if player_location.screen_cell is not None:
            player_cell = next(
                (
                    item.crop
                    for item in mapping.scan.cells
                    if (item.crop.column, item.crop.row) == player_location.screen_cell
                ),
                None,
            )
            if player_cell is not None:
                center_x, center_y = player_cell.center
                tile = self.extractor.tile_size_px
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
                label = f"PLAYER {player_location.source.value.upper()}"
                for image in (grid, tracking, hostility):
                    cv2.polylines(image, [points], True, (255, 180, 0), 2)
                    cv2.putText(image, label, (max(0, center_x - 90), max(16, center_y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 180, 0), 1)
        return grid, components, entity_image, tracking, hostility
