from __future__ import annotations

import numpy as np

from kage_combat_lab.domain import GridCell
from kage_combat_lab.occupancy_model import (
    CellOccupancy,
    DiffSource,
    OccupancyCluster,
    OccupancyState,
)
from kage_combat_lab.runtime_semantic_entity import (
    DangerAffinity,
    _level,
    _plausible_cluster,
    _prior,
)
from kage_combat_lab.runtime_trainer_suspension import (
    suspend_trainer_detector_for_validation,
)
from kage_combat_lab.tile_perception import TileClass, TileEvidence


def _evidence(cell: GridCell) -> TileEvidence:
    return TileEvidence(
        cell=cell,
        bbox=(cell.x * 64, cell.y * 64, 64, 64),
        category=TileClass.UNKNOWN,
        similarity=0.86,
        novelty=0.14,
        known_terrain=False,
        temporal_activity=0.05,
        activity_bbox=None,
        matched_example_id="danger-like",
    )


def _cell(source: DiffSource) -> CellOccupancy:
    cell = GridCell(1, 1)
    return CellOccupancy(
        cell=cell,
        evidence=_evidence(cell),
        state=OccupancyState.OCCUPIED,
        diff_source=source,
        true_changed_ratio=0.22,
        bbox_coverage_ratio=0.0,
        largest_blob_area=620,
        blob_width=28,
        blob_height=48,
        edge_delta=0.2,
        color_delta=0.3,
        occupancy_score=0.84,
        danger_prior=0.0,
        persistence=2,
        mask=np.ones((64, 64), dtype=np.uint8) * 255,
        blob_bbox=(14, 8, 28, 48),
        reference_authoritative=source is DiffSource.EXACT_CELL_BASELINE,
    )


def _cluster(source: DiffSource, *, width: int = 28, height: int = 48):
    item = _cell(source)
    return OccupancyCluster(
        local_id=1,
        cells=frozenset({item.cell}),
        bbox=(78, 72, width, height),
        foot_point=(92.0, 120.0),
        foot_cell=item.cell,
        occupancy_score=0.84,
        danger_prior=0.0,
        true_changed_ratio=0.22,
        largest_blob_area=620,
        raw_track_ids=frozenset(),
        cell_observations=(item,),
        authoritative_cells=1 if source is DiffSource.EXACT_CELL_BASELINE else 0,
    )


def test_unknown_preserves_likely_danger_affinity(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_DANGER_CONFIRMED_SIMILARITY", "0.90")
    monkeypatch.setenv("KAGE_PR26_DANGER_LIKELY_SIMILARITY", "0.82")
    monkeypatch.setenv("KAGE_PR26_DANGER_WEAK_SIMILARITY", "0.72")
    monkeypatch.setenv("KAGE_PR26_DANGER_MARGIN", "0.04")

    assert _level(0.86, 0.08, TileClass.UNKNOWN) == "DANGER_LIKELY"


def test_unknown_preserves_weak_danger_affinity(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_DANGER_CONFIRMED_SIMILARITY", "0.90")
    monkeypatch.setenv("KAGE_PR26_DANGER_LIKELY_SIMILARITY", "0.82")
    monkeypatch.setenv("KAGE_PR26_DANGER_WEAK_SIMILARITY", "0.72")
    monkeypatch.setenv("KAGE_PR26_DANGER_MARGIN", "0.04")

    assert _level(0.76, -0.03, TileClass.UNKNOWN) == "DANGER_WEAK_PRIOR"


def test_confirmed_danger_keeps_full_priority() -> None:
    affinity = DangerAffinity(
        best_category=TileClass.DANGER,
        best_similarity=0.94,
        danger_similarity=0.94,
        best_non_danger_similarity=0.75,
        danger_margin=0.19,
        level="DANGER_CONFIRMED",
    )

    assert _prior(affinity) == 0.94


def test_exact_baseline_humanoid_cluster_can_form_entity_lock() -> None:
    assert _plausible_cluster(_cluster(DiffSource.EXACT_CELL_BASELINE))


def test_class_reference_cluster_cannot_form_entity_lock() -> None:
    assert not _plausible_cluster(_cluster(DiffSource.CLASS_REFERENCE))


def test_oversized_cluster_cannot_form_entity_lock() -> None:
    assert not _plausible_cluster(
        _cluster(DiffSource.EXACT_CELL_BASELINE, width=192, height=256)
    )


def test_trainer_template_scan_is_suspended_in_perception_only(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "PERCEPTION_ONLY")

    class FakeDetector:
        def _best_visual(self, frame_bgr, *, arena_rect=None):
            return "expensive-result"

    assert suspend_trainer_detector_for_validation(FakeDetector)
    detector = FakeDetector()
    detector.last_template_scores = {"old": 1.0}
    detector.last_template_scales = {"old": 1.0}
    detector.last_accepted_template_mode = "64"
    detector.last_accepted_template_source = "old"
    detector.last_rejection_reason = ""
    detector.last_raw_score = 1.0
    detector.last_raw_scale = 1.0
    detector.last_raw_location = (0, 0)
    detector.last_raw_template_mode = "64"
    detector.last_raw_template_source = "old"

    assert detector._best_visual(np.zeros((64, 64, 3), dtype=np.uint8)) is None
    assert detector.last_rejection_reason == "suspended-during-validation"


def test_trainer_template_scan_is_not_suspended_in_full_combat(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FULL_COMBAT")

    class FakeDetector:
        def _best_visual(self, frame_bgr, *, arena_rect=None):
            return "kept"

    assert not suspend_trainer_detector_for_validation(FakeDetector)
    assert FakeDetector()._best_visual(None) == "kept"
