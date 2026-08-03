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
    TileKnowledgeState,
)
from .overlay_detector import OverlayDetector
from .player_locator import PlayerLocator


TERRAIN_CLASSES = {
    "walkable",
    "wall",
    "walkable_with_jutsu",
    "transition",
    "danger",
}

SEMANTIC_ENTITY_CLASSES = {
    "npc",
    "blocking_object",
    "ignore_dynamic",
}

EXPLICIT_REPERTOIRE_SOURCES = {
    "taught_tile",
    "manual_confirmation",
}


class EnemyPerceptionEngine:
    """Passive local perception over an explicitly taught tile repertoire.

    The physical file name ``02_background_composite.png`` is retained for
    compatibility, but its content is no longer a reconstructed background.
    It is always the real captured frame plus repertoire-state annotations.

    Two independent paths feed the tracker:
    1. semantic NPC candidates, which never require a terrain reference;
    2. localized foreign bodies over a valid explicitly taught terrain match.
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
        scene_consensus: Any | None = None,
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
            raise ValueError(
                "background thresholds must satisfy diagnostic <= usable <= strong"
            )
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
        # Kept only for constructor compatibility. It is intentionally not used
        # to create or authorize operational repertoire matches.
        self.scene_consensus = scene_consensus
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

    @staticmethod
    def _repertoire_color(state: TileKnowledgeState) -> tuple[int, int, int]:
        return {
            TileKnowledgeState.KNOWN_CLEAN: (0, 170, 0),
            TileKnowledgeState.KNOWN_WITH_FOREIGN_BODY: (0, 140, 255),
            TileKnowledgeState.SEMANTIC_ENTITY: (255, 0, 255),
            TileKnowledgeState.UNKNOWN_TILE: (70, 70, 220),
            TileKnowledgeState.PLAYER_CELL: (255, 180, 0),
            TileKnowledgeState.OUTSIDE_ROI: (80, 80, 80),
            TileKnowledgeState.OUTSIDE_PLAYFIELD: (55, 55, 55),
        }[state]

    @staticmethod
    def _repertoire_label(
        state: TileKnowledgeState,
        semantic_class: str,
        semantic_confidence: float,
        foreign_body_ratio: float,
    ) -> str | None:
        if state == TileKnowledgeState.KNOWN_WITH_FOREIGN_BODY:
            return f"FOREIGN BODY {foreign_body_ratio:.0%}"
        if state == TileKnowledgeState.SEMANTIC_ENTITY:
            return f"{semantic_class.upper()} {semantic_confidence:.0%}"
        if state == TileKnowledgeState.UNKNOWN_TILE:
            return "UNKNOWN"
        if state == TileKnowledgeState.PLAYER_CELL:
            return "PLAYER"
        return None

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
        remaining = {
            (item.crop.column, item.crop.row): item for item in semantic_cells
        }
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
            average_column = sum(cell.column for cell in cells) / len(cells)
            anchor_cell = max(
                cells,
                key=lambda cell: (
                    cell.row,
                    -abs(cell.column - average_column),
                ),
            )
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
            confidence = max(
                float(item.classification.confidence) for item in group
            )
            matched = max(
                group,
                key=lambda item: item.classification.confidence,
            ).classification.matched_example_id
            classification = EntityClassification(
                EntityClass.NEUTRAL_NPC,
                confidence,
                True,
                matched,
            )
            feature = self.classifier.knowledge.extractor.extract(
                region.crop,
                region.mask,
            )
            repertoire = background_by_cell.get(anchor_screen, {})
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
                    background_cluster_id=repertoire.get("cluster_id"),
                    background_confidence=float(repertoire.get("score", 0.0)),
                    background_match_level=str(
                        repertoire.get("level", BackgroundMatchLevel.NONE.value)
                    ),
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
            events.append(
                {"event": "player_lost", "frame": mapping.frame_index}
            )
        if (
            self.backgrounds.outdated_schema_detected
            and not self._schema_warning_emitted
        ):
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
        background_by_cell: dict[tuple[int, int], dict[str, Any]] = {}

        # The physical file name is intentionally preserved. Its content is now
        # the real frame plus repertoire annotations. No reference image is ever
        # copied into a cell of this image.
        background_composite = frame.copy()
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
            "known_clean_tiles": 0,
            "foreign_body_tiles": 0,
            "semantic_entity_tiles": 0,
            "unknown_tiles": 0,
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
            inside_playfield = self.playfield_scope.is_eligible(
                item,
                frame_height,
            )
            screen_distance = self._manhattan(screen_cell, player_screen)
            inside_processing_roi = bool(
                inside_playfield
                and screen_distance is not None
                and screen_distance <= self.processing_radius_cells
            )
            counters["cells_inside_playfield"] += int(inside_playfield)
            counters["cells_inside_processing_roi"] += int(
                inside_processing_roi
            )

            is_player_cell = bool(
                player_screen is not None and screen_cell == player_screen
            )
            is_semantic_entity = bool(
                classification.known
                and semantic_class in SEMANTIC_ENTITY_CLASSES
                and inside_playfield
                and inside_processing_roi
                and not is_player_cell
            )
            is_semantic_npc = bool(
                is_semantic_entity
                and semantic_class == "npc"
                and classification.confidence >= self.semantic_entity_threshold
                and screen_distance is not None
                and screen_distance <= self.interest_radius_cells
            )
            if is_semantic_npc:
                semantic_cells.append(item)

            match = None
            level = BackgroundMatchLevel.NONE
            metrics = OverlayMetrics()
            operational_allowed = False
            rejected_reason: str | None = None
            decision = "unknown_tile"
            decision_reason = "no_valid_taught_repertoire_match"
            tile_state = TileKnowledgeState.UNKNOWN_TILE
            valid_repertoire_match = False
            full_match_score = 0.0
            preserved_terrain_score = 0.0
            foreign_body_ratio = 0.0

            if not inside_playfield:
                tile_state = TileKnowledgeState.OUTSIDE_PLAYFIELD
                decision = "outside_playfield"
                decision_reason = "hud_excluded"
            elif not player_location.recognized:
                tile_state = TileKnowledgeState.UNKNOWN_TILE
                decision = "no_player_anchor"
                decision_reason = "player_not_located"
            elif not inside_processing_roi:
                tile_state = TileKnowledgeState.OUTSIDE_ROI
                decision = "outside_interest_radius"
                decision_reason = (
                    f"distance_greater_than_{self.processing_radius_cells}"
                )
            elif is_player_cell:
                tile_state = TileKnowledgeState.PLAYER_CELL
                decision = "player_cell"
                decision_reason = f"player_{player_location.source.value}"
            elif not mapping.settled:
                tile_state = TileKnowledgeState.UNKNOWN_TILE
                decision = "moving_frame"
                decision_reason = "frame_not_settled"
            elif is_semantic_entity:
                tile_state = TileKnowledgeState.SEMANTIC_ENTITY
                decision = "semantic_entity"
                decision_reason = f"known_semantic_{semantic_class}"
                counters["semantic_entity_tiles"] += 1
            else:
                match_class = (
                    semantic_class if semantic_class in TERRAIN_CLASSES else None
                )
                match = self.backgrounds.choose(
                    cell.image,
                    terrain_class=match_class,
                    allowed_sources=EXPLICIT_REPERTOIRE_SOURCES,
                )
                if match.available and match.image is not None:
                    level = self._match_level(match.confidence)
                    match.match_level = level
                    full_match_score = float(match.raw_similarity)
                    preserved_terrain_score = float(
                        self.backgrounds.robust_similarity(
                            cell.image,
                            match.image,
                        )
                    )
                    overlay = self.detector.detect(cell.image, match.image)
                    metrics = overlay.metrics
                    structural = bool(
                        metrics.changed_pixel_ratio
                        >= self.max_background_changed_ratio
                        or metrics.difference_mean
                        >= self.max_background_mean_difference
                    )
                    clean_match = bool(
                        full_match_score >= self.background_strong_threshold
                        and not metrics.overlay_detected
                    )
                    localized_foreign_body = bool(
                        match.confidence >= self.background_usable_threshold
                        and full_match_score
                        >= self.background_diagnostic_threshold
                        and preserved_terrain_score
                        >= self.background_strong_threshold
                        and metrics.overlay_detected
                        and metrics.component_count > 0
                        and not structural
                    )

                    if clean_match:
                        tile_state = TileKnowledgeState.KNOWN_CLEAN
                        valid_repertoire_match = True
                        decision = "known_clean"
                        decision_reason = "known_clean_taught_tile"
                        counters["known_clean_tiles"] += 1
                        background_by_cell[screen_cell] = {
                            "cluster_id": match.cluster_id,
                            "score": match.confidence,
                            "level": level.value,
                        }
                        events.append(
                            {
                                "event": "tile_known_clean",
                                "frame": mapping.frame_index,
                                "screen_cell": list(screen_cell),
                                "reference_id": match.reference_id,
                            }
                        )
                    elif localized_foreign_body:
                        tile_state = (
                            TileKnowledgeState.KNOWN_WITH_FOREIGN_BODY
                        )
                        valid_repertoire_match = True
                        operational_allowed = True
                        foreign_body_ratio = float(
                            metrics.changed_pixel_ratio
                        )
                        decision = "known_with_foreign_body"
                        decision_reason = (
                            "known_taught_tile_with_localized_foreign_body"
                        )
                        counters["foreign_body_tiles"] += 1
                        counters["diagnostic_differences"] += 1
                        counters["operational_differences"] += 1
                        background_by_cell[screen_cell] = {
                            "cluster_id": match.cluster_id,
                            "score": match.confidence,
                            "level": level.value,
                        }
                        tile_size = (
                            cell.x1 - cell.x0,
                            cell.y1 - cell.y0,
                        )
                        difference = cv2.resize(
                            overlay.difference,
                            tile_size,
                            interpolation=cv2.INTER_NEAREST,
                        )
                        mask = cv2.resize(
                            overlay.mask,
                            tile_size,
                            interpolation=cv2.INTER_NEAREST,
                        )
                        difference_composite[
                            cell.y0 : cell.y1,
                            cell.x0 : cell.x1,
                        ] = difference
                        mask_composite[
                            cell.y0 : cell.y1,
                            cell.x0 : cell.x1,
                        ] = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                        residual_cell_results.append(
                            (cell, overlay, world_cell)
                        )
                        events.extend(
                            [
                                {
                                    "event": "tile_known_with_foreign_body",
                                    "frame": mapping.frame_index,
                                    "screen_cell": list(screen_cell),
                                    "reference_id": match.reference_id,
                                    "foreign_body_ratio": foreign_body_ratio,
                                },
                                {
                                    "event": "foreign_body_candidate_created",
                                    "frame": mapping.frame_index,
                                    "screen_cell": list(screen_cell),
                                    "reference_id": match.reference_id,
                                },
                            ]
                        )
                    else:
                        tile_state = TileKnowledgeState.UNKNOWN_TILE
                        rejected_reason = (
                            "structural_repertoire_mismatch"
                            if structural
                            else "no_valid_taught_repertoire_match"
                        )
                        decision = "unknown_tile"
                        decision_reason = rejected_reason
                        counters["unknown_tiles"] += 1
                        events.extend(
                            [
                                {
                                    "event": "repertoire_match_rejected",
                                    "frame": mapping.frame_index,
                                    "screen_cell": list(screen_cell),
                                    "best_candidate_id": match.reference_id,
                                    "best_candidate_score": match.confidence,
                                    "reason": rejected_reason,
                                },
                                {
                                    "event": "unknown_tile_detected",
                                    "frame": mapping.frame_index,
                                    "screen_cell": list(screen_cell),
                                },
                            ]
                        )
                else:
                    tile_state = TileKnowledgeState.UNKNOWN_TILE
                    decision = "unknown_tile"
                    decision_reason = "no_taught_repertoire_candidate"
                    counters["unknown_tiles"] += 1
                    events.append(
                        {
                            "event": "unknown_tile_detected",
                            "frame": mapping.frame_index,
                            "screen_cell": list(screen_cell),
                        }
                    )

            if level == BackgroundMatchLevel.STRONG:
                counters["background_matches_strong"] += 1
            elif level == BackgroundMatchLevel.USABLE:
                counters["background_matches_usable"] += 1
            elif level == BackgroundMatchLevel.WEAK:
                counters["background_matches_weak"] += 1
            elif match is not None and match.available:
                counters["background_matches_rejected"] += 1

            color = self._repertoire_color(tile_state)
            thickness = (
                2
                if tile_state
                in {
                    TileKnowledgeState.KNOWN_WITH_FOREIGN_BODY,
                    TileKnowledgeState.SEMANTIC_ENTITY,
                    TileKnowledgeState.UNKNOWN_TILE,
                    TileKnowledgeState.PLAYER_CELL,
                }
                else 1
            )
            cv2.rectangle(
                background_composite,
                (cell.x0, cell.y0),
                (cell.x1 - 1, cell.y1 - 1),
                color,
                thickness,
            )
            label = self._repertoire_label(
                tile_state,
                semantic_class,
                classification.confidence,
                foreign_body_ratio,
            )
            if label:
                cv2.putText(
                    background_composite,
                    label,
                    (cell.x0 + 2, min(cell.y1 - 3, cell.y0 + 13)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.32,
                    color,
                    1,
                    cv2.LINE_AA,
                )
            if tile_state == TileKnowledgeState.UNKNOWN_TILE:
                cv2.putText(
                    difference_composite,
                    "UNKNOWN",
                    (cell.x0 + 2, min(cell.y1 - 3, cell.y0 + 13)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.30,
                    (120, 120, 120),
                    1,
                    cv2.LINE_AA,
                )

            matched_id = (
                match.reference_id
                if match is not None
                and match.available
                and valid_repertoire_match
                else None
            )
            matched_class = (
                match.terrain_class
                if match is not None
                and match.available
                and valid_repertoire_match
                else None
            )
            record = CellDebugRecord(
                screen_cell=screen_cell,
                world_cell=world_cell,
                pixel_bounds=(cell.x0, cell.y0, cell.x1, cell.y1),
                terrain_class=semantic_class,
                terrain_confidence=classification.confidence,
                background_reference_available=valid_repertoire_match,
                background_reference_id=matched_id,
                background_reference_confidence=(
                    match.confidence
                    if match is not None and valid_repertoire_match
                    else 0.0
                ),
                metrics=metrics,
                decision=decision,
                decision_reason=decision_reason,
                inside_playfield=inside_playfield,
                inside_processing_roi=inside_processing_roi,
                background_reference_rejected=bool(rejected_reason),
                background_reference_rejection_reason=rejected_reason,
                background_reference_terrain_class=matched_class,
                background_reference_source_world_cell=(
                    match.source_world_cell
                    if match is not None and valid_repertoire_match
                    else None
                ),
                player_location_source=player_location.source.value,
                best_background_cluster_id=(
                    match.cluster_id
                    if match is not None and match.available
                    else None
                ),
                best_background_score=(
                    match.confidence
                    if match is not None and match.available
                    else 0.0
                ),
                background_match_level=level.value,
                diagnostic_difference_generated=operational_allowed,
                operational_difference_allowed=operational_allowed,
                semantic_candidate_created=is_semantic_npc,
                residual_candidate_created=operational_allowed,
                tile_knowledge_state=tile_state.value,
                valid_repertoire_match=valid_repertoire_match,
                matched_repertoire_example_id=matched_id,
                matched_repertoire_class=matched_class,
                best_diagnostic_candidate_id=(
                    match.reference_id
                    if match is not None and match.available
                    else None
                ),
                best_diagnostic_score=(
                    match.confidence
                    if match is not None and match.available
                    else 0.0
                ),
                full_match_score=full_match_score,
                preserved_terrain_score=preserved_terrain_score,
                foreign_body_ratio=foreign_body_ratio,
                difference_operational=operational_allowed,
                candidate_created=bool(
                    is_semantic_npc or operational_allowed
                ),
            )
            cell_records.append(record)
            record_by_screen[screen_cell] = record

        # Scene consensus is deliberately disconnected. Repeated observations
        # can no longer create operational repertoire entries automatically.

        semantic_observations, semantic_rejections = (
            self._semantic_observations(
                frame,
                semantic_cells,
                player_screen,
                player_world,
                mapping.frame_index,
                background_by_cell,
            )
        )
        counters["semantic_candidates"] = len(semantic_observations)
        for observation in semantic_observations:
            events.append(
                {
                    "event": "semantic_entity_detected",
                    "frame": mapping.frame_index,
                    "semantic_class": observation.semantic_class,
                    "confidence": observation.semantic_confidence,
                    "anchor_world_cell": observation.region.anchor_world_cell,
                    "distance": observation.distance_to_player,
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
                events.append(
                    {
                        "event": "component_rejected",
                        "frame": mapping.frame_index,
                        **rejection,
                    }
                )
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
                background_cluster_id=(
                    record.best_background_cluster_id if record else None
                ),
                background_confidence=(
                    record.best_background_score if record else 0.0
                ),
                background_match_level=(
                    record.background_match_level
                    if record
                    else BackgroundMatchLevel.NONE.value
                ),
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
                    "authorized_by": (
                        TileKnowledgeState.KNOWN_WITH_FOREIGN_BODY.value
                    ),
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
            int(event.get("event") == "entity_created")
            for event in tracking_events
        )
        tracked_observations = [
            item for item in observations if item.track_id
        ]
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
            session_id=(
                self.recorder.session_id if self.recorder else "runtime"
            ),
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
                "explicit_repertoire_references": (
                    self.backgrounds.reference_count(
                        EXPLICIT_REPERTOIRE_SOURCES
                    )
                ),
                "operational_sources": sorted(
                    EXPLICIT_REPERTOIRE_SOURCES
                ),
                "scene_consensus_operational": False,
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

        for image in (
            grid,
            components,
            entity_image,
            tracking,
            hostility,
        ):
            shade = image.copy()
            cv2.rectangle(
                shade,
                (0, playfield_cutoff),
                (width - 1, height - 1),
                (25, 25, 25),
                -1,
            )
            cv2.addWeighted(shade, 0.65, image, 0.35, 0.0, image)
            cv2.line(
                image,
                (0, playfield_cutoff),
                (width - 1, playfield_cutoff),
                (0, 0, 255),
                2,
            )

        for cell in cells:
            x0, y0, x1, y1 = cell.pixel_bounds
            state = TileKnowledgeState(cell.tile_knowledge_state)
            color = self._repertoire_color(state)
            thickness = (
                2
                if state
                in {
                    TileKnowledgeState.KNOWN_WITH_FOREIGN_BODY,
                    TileKnowledgeState.SEMANTIC_ENTITY,
                    TileKnowledgeState.UNKNOWN_TILE,
                }
                else 1
            )
            cv2.rectangle(
                grid,
                (x0, y0),
                (x1 - 1, y1 - 1),
                color,
                thickness,
            )
            labels: list[str] = []
            if cell.semantic_candidate_created:
                labels.append(f"NPC {cell.terrain_confidence:.0%}")
            if state == TileKnowledgeState.KNOWN_WITH_FOREIGN_BODY:
                labels.append(f"FOREIGN {cell.foreign_body_ratio:.0%}")
            elif state == TileKnowledgeState.UNKNOWN_TILE:
                labels.append("UNKNOWN")
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
            cv2.rectangle(
                components,
                (x0, y0),
                (x1, y1),
                (255, 0, 255),
                2,
            )
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
            cv2.rectangle(
                components,
                (x0, y0),
                (x1, y1),
                (0, 215, 255),
                1,
            )
            cv2.putText(
                components,
                "FOREIGN BODY",
                (x0, max(12, y0 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                (0, 215, 255),
                1,
            )
        for region, validation in rejected_regions:
            x0, y0, x1, y1 = region.bounding_box_px
            cv2.rectangle(
                components,
                (x0, y0),
                (x1, y1),
                (150, 150, 150),
                2,
            )
            cv2.putText(
                components,
                validation.reason[:24],
                (x0, max(12, y0 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                (210, 210, 210),
                1,
            )

        for observation in entities:
            x0, y0, x1, y1 = observation.region.bounding_box_px
            source = "+".join(observation.candidate_sources) or "unknown"
            cv2.rectangle(
                entity_image,
                (x0, y0),
                (x1, y1),
                (0, 215, 255),
                2,
            )
            cv2.putText(
                entity_image,
                source,
                (x0, max(12, y0 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (0, 215, 255),
                1,
            )
            cv2.rectangle(
                tracking,
                (x0, y0),
                (x1, y1),
                (0, 165, 255),
                2,
            )
            cv2.putText(
                tracking,
                (
                    f"{observation.track_id} "
                    f"D={observation.distance_to_player} "
                    f"{observation.movement_state}"
                ),
                (x0, max(12, y0 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (0, 165, 255),
                1,
            )
            color = (
                (0, 0, 255)
                if observation.hostility_score >= 12
                else (0, 165, 255)
            )
            cv2.rectangle(
                hostility,
                (x0, y0),
                (x1, y1),
                color,
                2,
            )
            cv2.putText(
                hostility,
                (
                    f"{observation.hostility_state.value} "
                    f"{observation.hostility_score}"
                ),
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
                    if (item.crop.column, item.crop.row)
                    == player_location.screen_cell
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
                label = (
                    f"PLAYER {player_location.source.value.upper()}"
                )
                for image in (grid, tracking, hostility):
                    cv2.polylines(
                        image,
                        [points],
                        True,
                        (255, 180, 0),
                        2,
                    )
                    cv2.putText(
                        image,
                        label,
                        (max(0, center_x - 90), max(16, center_y - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.40,
                        (255, 180, 0),
                        1,
                    )
        return grid, components, entity_image, tracking, hostility
